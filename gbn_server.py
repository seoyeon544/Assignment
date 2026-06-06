import argparse
import os
import socket
import time

from common import (
    PACKET_SIZE,
    DATA_SIZE,
    SEQ_RANGE,
    make_packet,
    parse_packet,
)


FLAGS = None
DEBUG = False

# Data: 최대 1456 Bytes
def read_file_chunks(file_path: str):

    chunks = []

    with open(file_path, 'rb') as f:
        while True:
            data = f.read(DATA_SIZE)

            if not data:
                break

            chunks.append(data)

    return chunks

# ACK 번호를 실제 패킷 인덱스로 변환하는 함수
def ack_to_absolute_index(ack_seq, base, next_to_send, total_packets):
    
    upper = min(next_to_send, total_packets) # 현재 전송된 범위의 끝

    # base 다음 위치부터 현재 전송된 범위까지
    for candidate in range(base + 1, upper + 1):
        # 해당 인덱스의 sequence number가 ACK 번호와 같으면, 거기까지는 수신 완료임
        if candidate % SEQ_RANGE == ack_seq: 
            return candidate

    # ACK 번호가 현재 base와 같으면, window를 이동하지 않음
    if base % SEQ_RANGE == ack_seq:
        return base

    return base


# Go Back N 방식으로 파일을 전송하는 함수
def send_file_go_back_n(sock, client, chunks):

    # ACK를 기다릴 timeout 설정
    sock.settimeout(FLAGS.timeout)

    total_packets = len(chunks)

    base = 0 # ACK를 받지 않은 맨 앞 패킷 인덱스
    next_to_send = 0 # 다음에 전송할 패킷 인덱스

    # base가 전체 패킷 수에 도달할 때까지
    # 에러 제어 Case 3) 파일의 마지막 데이터 패킷을 보냈는데 클라이언트에 제대로 도착하지 않음
    while base < total_packets:

        # 아직 보낼 패킷이 남아있고, base+ window 사이즈보다 다음에 전송할 패킷 인덱스가 작은경우, 보낼 수 있는 패킷을 연속으로 전송
        while next_to_send < total_packets and next_to_send < base + FLAGS.window_size:
            seq = next_to_send % SEQ_RANGE # sequence number range: 0~15
            packet = make_packet(seq, chunks[next_to_send])

            print(f'[Server][GBN] Sending packet index={next_to_send}, seq={seq}')
            sock.sendto(packet, client)

            next_to_send += 1

        try:
            ack_packet, _ = sock.recvfrom(PACKET_SIZE)
            ack, _, valid = parse_packet(ack_packet)

            print(f'[Server][GBN] Received ACK={ack}, valid={valid}')

            # 손상된 ACK drop
            if not valid:
                print('[Server][GBN] Invalid ACK checksum. Ignore.')
                continue

            # ACK 번호를 패킷 인덱스로 변환
            new_base = ack_to_absolute_index(
                ack_seq=ack,
                base=base,
                next_to_send=next_to_send,
                total_packets=total_packets
            )

            # 새로운 base가 기존 base보다 크면 window를 앞으로 이동
            if new_base > base:
                print(f'[Server][GBN] Slide window: base {base} -> {new_base}')
                base = new_base

        # 에러 제어 Case 1) 서버가 보낸 데이터 패킷이 클라이언트에 제대로 도착하지 않음
        except socket.timeout:
            print(f'[Server][GBN] Timer expired. Go back to base={base}')
            next_to_send = base

    # timeout 해제
    sock.settimeout(None)
    print('[Server][GBN] File transfer complete')


def main():
    if DEBUG:
        print(f'Parsed arguments {FLAGS}')

    if FLAGS.window_size >= SEQ_RANGE:
        raise ValueError('window_size must be smaller than sequence number range 16.')

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((FLAGS.address, FLAGS.port))

    print(f'[Server] Listening on {FLAGS.address}:{FLAGS.port}')
    print(f'[Server] File directory: {FLAGS.directory}')
    print(f'[Server] Window size: {FLAGS.window_size}')

    while True:
        try:
            request, client = sock.recvfrom(PACKET_SIZE)
            message = request.decode('utf-8', errors='ignore').strip()

            print(f'[Server] Received "{message}" from {client}')

            if message.startswith('INFO '):
                filename = message.split(' ', 1)[1]
                file_path = os.path.join(FLAGS.directory, filename)

                if os.path.isfile(file_path):
                    file_size = os.path.getsize(file_path)
                    sock.sendto(str(file_size).encode('utf-8'), client)
                    print(f'[Server] Send file size: {file_size} bytes')
                else:
                    sock.sendto(b'404 Not Found', client)
                    print('[Server] File not found')

            elif message.startswith('DOWNLOAD '):
                filename = message.split(' ', 1)[1]
                file_path = os.path.join(FLAGS.directory, filename)

                if not os.path.isfile(file_path):
                    sock.sendto(b'404 Not Found', client)
                    print('[Server] File not found')
                    continue

                chunks = read_file_chunks(file_path)

                print(f'[Server] Download start: {filename}')
                print(f'[Server] Total packets: {len(chunks)}')
                print(f'[Server] Data size per packet: {DATA_SIZE} bytes')

                start_time = time.time()

                send_file_go_back_n(sock, client, chunks)

                end_time = time.time()

                print(f'[Server] Elapsed time: {end_time - start_time:.6f} sec')

        except KeyboardInterrupt:
            print(f'\n[Server] Shutting down... {sock}')
            break


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('--debug', action='store_true')
    parser.add_argument('--address', type=str, default='0.0.0.0')
    parser.add_argument('--port', type=int, default=3034)
    parser.add_argument('--directory', type=str, default='files')
    parser.add_argument('--timeout', type=float, default=0.5)
    parser.add_argument('--window_size', type=int, default=4)

    FLAGS, _ = parser.parse_known_args()
    DEBUG = FLAGS.debug

    main()