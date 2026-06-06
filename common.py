import struct

# 과제 상수
PACKET_SIZE = 1500
SEQ_ACK_SIZE = 2
CHECKSUM_SIZE = 2
HEADER_SIZE = SEQ_ACK_SIZE + CHECKSUM_SIZE
DATA_SIZE = 1456
SEQ_RANGE = 16


# checksum을 계산하는 함수
def calculate_checksum(data: bytes) -> int:

    # 데이터 길이가 홀수이면, 마지막에 0x00을 붙여 2바이트 단위로 맞춤
    if len(data) % 2 == 1:
        data += b'\x00'

    total = 0

    # 2바이트씩 읽어서 16비트 정수로 더함
    for i in range(0, len(data), 2):
        word = (data[i] << 8) + data[i + 1]
        total += word

        total = (total & 0xFFFF) + (total >> 16) # 캐리가 발생하면 하위 16비트에 다시 더함

    total = (total & 0xFFFF) + (total >> 16) # 마지막 캐리 처리를 한 번 더

    return (~total) & 0xFFFF # 1의 보수 반환


# 데이터 패킷, ACK 패킷을 생성하는 함수
def make_packet(seq_ack: int, payload: bytes = b'') -> bytes:
    """
    데이터 패킷 또는 ACK 패킷을 생성한다.

    데이터 패킷:
    [Seq 2B][Checksum 2B][Data]

    ACK 패킷:
    [Ack 2B][Checksum 2B]
    """

    seq_ack = seq_ack % SEQ_RANGE # Sequence number range: 0~15
    seq_bytes = struct.pack('>H', seq_ack)

    checksum = calculate_checksum(seq_bytes + payload) # Seq/Ack 포함 Payload 전부
    checksum_bytes = struct.pack('>H', checksum)

    return seq_bytes + checksum_bytes + payload


# 패킷에서 Seq/Ack, Payload, Checksum 정상 여부를 반환하는 함수
def parse_packet(packet: bytes):

    if len(packet) < HEADER_SIZE:
        return None, b'', False

    seq_ack = struct.unpack('>H', packet[:2])[0]
    received_checksum = struct.unpack('>H', packet[2:4])[0]
    payload = packet[4:]

    calculated_checksum = calculate_checksum(packet[:2] + payload)

    valid = received_checksum == calculated_checksum

    return seq_ack, payload, valid