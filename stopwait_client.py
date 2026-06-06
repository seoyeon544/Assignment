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


# stop and wait 방식으로 파일을 수신하는 함수
def receive_file_stop_and_wait(sock, server, filename, file_size):

    expected_seq = 0
    received_size = 0

    output_path = os.path.join(FLAGS.output_dir, 'downloaded_' + filename)

    last_ack_packet = make_packet(expected_seq)

    with open(output_path, 'wb') as f:
        while received_size < file_size:
            chunk, server = sock.recvfrom(FLAGS.chunk_maxsize)

            seq, data, valid = parse_packet(chunk)

            print(
                f'[Client][SW] Received seq={seq}, '
                f'valid={valid}, expected={expected_seq}'
            )

            if not valid:
                print('[Client][SW] Incorrect checksum packet arrived')
                sock.sendto(last_ack_packet, server)
                continue

            if seq != expected_seq:
                print('[Client][SW] Incorrect sequence packet arrived')
                sock.sendto(last_ack_packet, server)
                continue

            remain = file_size - received_size
            data_to_write = data[:remain]

            f.write(data_to_write)
            received_size += len(data_to_write)

            ack_num = (expected_seq + 1) % SEQ_RANGE
            ack_packet = make_packet(ack_num)

            sock.sendto(ack_packet, server)

            last_ack_packet = ack_packet
            expected_seq = ack_num

            print(
                f'[Client][SW] Send ACK={ack_num}, '
                f'received={received_size}/{file_size}'
            )

    close_wait_end = time.time() + FLAGS.timeout * 2
    print('[Client][SW] Close wait')

    while time.time() < close_wait_end:
        try:
            chunk, server = sock.recvfrom(FLAGS.chunk_maxsize)
            seq, _, valid = parse_packet(chunk)

            if valid:
                sock.sendto(last_ack_packet, server)
                print(f'[Client][SW] Duplicate packet seq={seq}. Resend last ACK.')

        except socket.timeout:
            break

    return output_path, received_size


def main():
    if DEBUG:
        print(f'Parsed arguments {FLAGS}')

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(FLAGS.timeout)

    server = (FLAGS.address, FLAGS.port)

    print(f'[Client] Ready to send using {sock}')
    print(f'[Client] Server: {server}')

    filename = FLAGS.filename

    if filename is None:
        filename = input('Filename: ').strip()

    info_request = f'INFO {filename}'
    sock.sendto(info_request.encode('utf-8'), server)

    print(f'[Client] Request INFO {filename} to {server}')

    response, _ = sock.recvfrom(FLAGS.chunk_maxsize)
    response = response.decode('utf-8', errors='ignore').strip()

    if response == '404 Not Found':
        print('[Client] File not found')
        return

    file_size = int(response)

    print(f'[Client] File size: {file_size} bytes')

    download_request = f'DOWNLOAD {filename}'

    start_time = time.time()

    sock.sendto(download_request.encode('utf-8'), server)

    print(f'[Client] Request DOWNLOAD {filename} to {server}')

    output_path, received_size = receive_file_stop_and_wait(
        sock=sock,
        server=server,
        filename=filename,
        file_size=file_size
    )

    end_time = time.time()

    elapsed_time = end_time - start_time
    throughput = (received_size * 8) / elapsed_time

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