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


def read_file_chunks(file_path: str):
    """
    파일을 DATA_SIZE(1456Bytes) 단위로 나누어 리스트에 저장한다.
    """

    chunks = []

    with open(file_path, 'rb') as f:
        while True:
            data = f.read(DATA_SIZE)

            if not data:
                break

            chunks.append(data)

    return chunks


def send_file_stop_and_wait(sock, client, chunks):
    """
    Stop-and-Wait ARQ 방식으로 파일을 전송한다.

    동작:
    1. 패킷 하나 전송
    2. ACK 대기
    3. 올바른 ACK가 오면 다음 패킷 전송
    4. timeout 또는 잘못된 ACK가 발생하면 같은 패킷 재전송
    """

    sock.settimeout(FLAGS.timeout)

    packet_index = 0
    total_packets = len(chunks)

    while packet_index < total_packets:
        seq = packet_index % SEQ_RANGE
        packet = make_packet(seq, chunks[packet_index])
        expected_ack = (seq + 1) % SEQ_RANGE

        while True:
            print(f'[Server][SW] Sending packet index={packet_index}, seq={seq}')
            sock.sendto(packet, client)

            try:
                ack_packet, _ = sock.recvfrom(PACKET_SIZE)
                ack, _, valid = parse_packet(ack_packet)

                print(
                    f'[Server][SW] Received ACK={ack}, '
                    f'valid={valid}, expected={expected_ack}'
                )

                # ACK가 정상이고, 다음에 받아야 할 seq 번호와 일치하면
                # 다음 패킷으로 이동한다.
                if valid and ack == expected_ack:
                    packet_index += 1
                    break

                print('[Server][SW] Wrong ACK or invalid checksum. Resend same packet.')

            except socket.timeout:
                # ACK가 일정 시간 동안 오지 않으면 같은 패킷을 다시 보낸다.
                print('[Server][SW] Timer expired. Resend same packet.')

    sock.settimeout(None)
    print('[Server][SW] File transfer complete')


def main():
    if DEBUG:
        print(f'Parsed arguments {FLAGS}')

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((FLAGS.address, FLAGS.port))

    print(f'[Server] Listening on {FLAGS.address}:{FLAGS.port}')
    print(f'[Server] File directory: {FLAGS.directory}')

    while True:
        try:
            request, client = sock.recvfrom(PACKET_SIZE)
            message = request.decode('utf-8', errors='ignore').strip()

            print(f'[Server] Received "{message}" from {client}')

            # INFO 파일명 요청 처리
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

            # DOWNLOAD 파일명 요청 처리
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

                send_file_stop_and_wait(sock, client, chunks)

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

    FLAGS, _ = parser.parse_known_args()
    DEBUG = FLAGS.debug

    main()