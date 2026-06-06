import argparse
import os
import socket
import time

from common import (
    SEQ_RANGE,
    make_packet,
    parse_packet,
)


FLAGS = None
DEBUG = False


# Go Back N 방식으로 수신하는 함수
def receive_file_go_back_n(sock, server, filename, file_size):

    expected_seq = 0 # 처음에는 seq=0 패킷을 기다림
    received_size = 0 # 파일에 저장한 바이트 수

    output_path = os.path.join(FLAGS.output_dir, 'downloaded_' + filename)

    last_ack_packet = make_packet(expected_seq) # 마지막으로 보낸 ACK를 저장 

    with open(output_path, 'wb') as f:
        while received_size < file_size:
            chunk, server = sock.recvfrom(FLAGS.chunk_maxsize)

            seq, data, valid = parse_packet(chunk) # 패킷에서 seq, data, checksum 결과를 분리

            print(
                f'[Client][GBN] Received seq={seq}, '
                f'valid={valid}, expected={expected_seq}'
            )

            # 원하는 패킷이 안 들어오면 drop
            # 1) checksum이 틀린 패킷 drop
            if not valid:
                print('[Client][GBN] Incorrect checksum packet arrived')
                sock.sendto(last_ack_packet, server)
                continue
            # 2) 기대한 seq 번호가 아니면 drop
            # 에러 제거 Case 2) 클라이언트가 보낸 ACK가 서버에 도착하지 않음
            if seq != expected_seq:
                print('[Client][GBN] Out-of-order packet arrived. Drop packet.')
                sock.sendto(last_ack_packet, server)
                continue

            # 정상 패킷이면 파일에 저장
            remain = file_size - received_size
            data_to_write = data[:remain]
            f.write(data_to_write)
            received_size += len(data_to_write)

            
            expected_seq = (expected_seq + 1) % SEQ_RANGE # 다음에 받아야 할 seq 번호로 변경
            ack_packet = make_packet(expected_seq)
            sock.sendto(ack_packet, server)

            last_ack_packet = ack_packet

            print(
                f'[Client][GBN] Send ACK={expected_seq}, '
                f'received={received_size}/{file_size}'
            )

    # 에러 제어 Case 4) 클라이언트가 파일을 다 받고 마지막 ACK를 보냈는데 서버에 도착하지 않음
    close_wait_end = time.time() + FLAGS.timeout * 2 # 마지막 ACK을 보내고 나서 Timer의 2배 대기
    print('[Client][GBN] Close wait')

    # 대기하는 동안
    while time.time() < close_wait_end:
        try: # 서버가 패킷을 보낸 경우
            chunk, server = sock.recvfrom(FLAGS.chunk_maxsize)
            seq, _, valid = parse_packet(chunk)
            # 정상 패킷인 경우, 마지막 ACK만 다시 전송
            if valid:
                sock.sendto(last_ack_packet, server)
                print(f'[Client][GBN] Duplicate packet seq={seq}. Resend last ACK.')
        # timeout 시간 동안 서버에서 아무 패킷도 오지 않으면, 종료
        except socket.timeout:
            break

    return output_path, received_size


def main():
    if DEBUG:
        print(f'Parsed arguments {FLAGS}')

    # UDP 소켓 생성
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # timeout 설정
    sock.settimeout(FLAGS.timeout)

    server = (FLAGS.address, FLAGS.port)

    print(f'[Client] Ready to send using {sock}')
    print(f'[Client] Server: {server}')

    filename = FLAGS.filename

    if filename is None:
        filename = input('Filename: ').strip()

    # 파일 정보 요펑 (Control message)
    info_request = f'INFO {filename}'
    sock.sendto(info_request.encode('utf-8'), server)

    print(f'[Client] Request INFO {filename} to {server}')

    response, _ = sock.recvfrom(FLAGS.chunk_maxsize)
    response = response.decode('utf-8', errors='ignore').strip()

    if response == '404 Not Found':
        print('[Client] File not found')
        return

    # 파일 크기
    file_size = int(response)
    print(f'[Client] File size: {file_size} bytes')

    # 파일 다운로드 요청
    download_request = f'DOWNLOAD {filename}'
    start_time = time.time() # 다운로드 시작 시간
    sock.sendto(download_request.encode('utf-8'), server)
    print(f'[Client] Request DOWNLOAD {filename} to {server}')

    output_path, received_size = receive_file_go_back_n(
        sock=sock,
        server=server,
        filename=filename,
        file_size=file_size
    )

    end_time = time.time() # 다운로드 종료 시간

    elapsed_time = end_time - start_time # 전체 다운로드 시간
    throughput = (received_size * 8) / elapsed_time # 처리량 계산 

    print('[Client] File download success')
    print(f'[Client] Saved path: {output_path}')
    print(f'[Client] Received {received_size} bytes after {elapsed_time:.6f} sec')
    print(f'[Client] Throughput: {throughput:,.0f} bps')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--address', type=str, required=True)
    parser.add_argument('--port', type=int, default=3034)
    parser.add_argument('--filename', type=str, default=None)
    parser.add_argument('--chunk_maxsize', type=int, default=2**16)
    parser.add_argument('--output_dir', type=str, default='downloads')
    parser.add_argument('--timeout', type=float, default=0.5)

    FLAGS, _ = parser.parse_known_args()
    DEBUG = FLAGS.debug

    os.makedirs(FLAGS.output_dir, exist_ok=True)

    main()