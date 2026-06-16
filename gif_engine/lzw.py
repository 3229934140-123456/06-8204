from typing import List, Tuple


def _read_bits(data: bytes, bit_offset: int, num_bits: int) -> Tuple[int, int]:
    value = 0
    for i in range(num_bits):
        byte_idx = (bit_offset + i) // 8
        bit_idx = (bit_offset + i) % 8
        if byte_idx >= len(data):
            return -1, bit_offset + num_bits
        if data[byte_idx] & (1 << bit_idx):
            value |= 1 << i
    return value, bit_offset + num_bits


def lzw_decode(compressed_data: bytes, min_code_size: int, expected_pixels: int) -> List[int]:
    if min_code_size < 2 or min_code_size > 8:
        raise ValueError(f"Invalid LZW minimum code size: {min_code_size}")

    clear_code = 1 << min_code_size
    eoi_code = clear_code + 1
    num_elems = eoi_code + 1
    code_size = min_code_size + 1

    dictionary: List[List[int]] = [[] for _ in range(4096)]
    for i in range(clear_code):
        dictionary[i] = [i]

    result: List[int] = []
    bit_offset = 0

    def get_next_code(cur_size, cur_offset):
        return _read_bits(compressed_data, cur_offset, cur_size)

    code, bit_offset = get_next_code(code_size, bit_offset)
    while code == clear_code:
        for i in range(clear_code):
            dictionary[i] = [i]
        num_elems = eoi_code + 1
        code_size = min_code_size + 1
        code, bit_offset = get_next_code(code_size, bit_offset)

    if code == eoi_code or code < 0:
        return []

    old_code = code
    result.extend(dictionary[old_code])
    c = dictionary[old_code][0]

    while len(result) < expected_pixels:
        code, bit_offset = get_next_code(code_size, bit_offset)
        if code < 0 or code == eoi_code:
            break

        if code == clear_code:
            for i in range(clear_code):
                dictionary[i] = [i]
            num_elems = eoi_code + 1
            code_size = min_code_size + 1
            code, bit_offset = get_next_code(code_size, bit_offset)
            while code == clear_code:
                code, bit_offset = get_next_code(code_size, bit_offset)
            if code < 0 or code == eoi_code:
                break
            old_code = code
            result.extend(dictionary[old_code])
            c = dictionary[old_code][0]
            continue

        if code < num_elems:
            in_string = list(dictionary[code])
        elif code == num_elems:
            in_string = list(dictionary[old_code]) + [c]
        else:
            raise ValueError(
                f"Corrupted LZW stream: code={code}, num_elems={num_elems}, old={old_code}, code_size={code_size}"
            )

        result.extend(in_string)
        c = in_string[0]

        if num_elems < 4096:
            dictionary[num_elems] = list(dictionary[old_code]) + [c]
            num_elems += 1

            if num_elems == (1 << code_size) and code_size < 12:
                code_size += 1

        old_code = code

    if len(result) > expected_pixels:
        result = result[:expected_pixels]

    return result


class _BitWriter:
    def __init__(self):
        self._buffer = bytearray()
        self._current_byte = 0
        self._bit_count = 0

    def write(self, value: int, num_bits: int) -> None:
        for i in range(num_bits):
            if value & (1 << i):
                self._current_byte |= 1 << self._bit_count
            self._bit_count += 1
            if self._bit_count == 8:
                self._buffer.append(self._current_byte)
                self._current_byte = 0
                self._bit_count = 0

    def get_bytes(self) -> bytes:
        if self._bit_count > 0:
            self._buffer.append(self._current_byte)
        return bytes(self._buffer)


def lzw_encode(pixel_indices: List[int], min_code_size: int) -> bytes:
    if min_code_size < 2 or min_code_size > 8:
        raise ValueError(f"Invalid LZW minimum code size: {min_code_size}")

    clear_code = 1 << min_code_size
    eoi_code = clear_code + 1

    if pixel_indices:
        max_idx = max(pixel_indices)
        if max_idx >= clear_code:
            raise ValueError(
                f"Pixel index {max_idx} exceeds max allowed value {clear_code - 1} "
                f"for min_code_size={min_code_size}."
            )

    code_size = min_code_size + 1
    num_elems = eoi_code + 1

    dictionary: dict = {}
    for i in range(clear_code):
        dictionary[(i,)] = i

    writer = _BitWriter()

    def emit_code(code):
        nonlocal code_size, num_elems
        writer.write(code, code_size)
        if num_elems == (1 << code_size) and code_size < 12:
            code_size += 1

    emit_code(clear_code)

    if not pixel_indices:
        emit_code(eoi_code)
        return writer.get_bytes()

    current = (pixel_indices[0],)

    for i in range(1, len(pixel_indices)):
        pixel = pixel_indices[i]
        extended = current + (pixel,)
        if extended in dictionary:
            current = extended
        else:
            emit_code(dictionary[current])

            if num_elems < 4096:
                dictionary[extended] = num_elems
                num_elems += 1

            if num_elems >= 4096:
                emit_code(clear_code)
                dictionary = {}
                for j in range(clear_code):
                    dictionary[(j,)] = j
                code_size = min_code_size + 1
                num_elems = eoi_code + 1

            current = (pixel,)

    emit_code(dictionary[current])
    emit_code(eoi_code)
    return writer.get_bytes()
