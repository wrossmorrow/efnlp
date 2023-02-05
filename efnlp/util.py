from __future__ import annotations

from gzip import compress as gzcompress, decompress as gzdecompress
from typing import List


def read_binary_file(name: str) -> bytes:
    with open(name, "rb") as f:
        data = f.read()
        if name.endswith(".gz"):
            data = gzdecompress(data)
        return data


def write_binary_file(name: str, data: bytes, compress: bool = True) -> None:
    if compress or name.endswith(".gz"):
        data = gzcompress(data)
    if compress and (not name.endswith(".gz")):
        name += ".gz"
    with open(name, "wb") as f:
        f.write(data)


def split_input(encoded: List[int], num_segments: int, block_size: int) -> List[List[int]]:

    remainder = len(encoded) % num_segments
    normalized_size = int((len(encoded) - remainder) / num_segments)
    if normalized_size <= block_size:
        raise ValueError("too many segments for specified block size")

    segment_sizes = [normalized_size + (1 if i < remainder else 0) for i in range(num_segments)]

    s, e = 0, segment_sizes[0]
    segments = []
    for i in range(num_segments):
        segments.append(encoded[max(0, s - block_size) : e])
        s += segment_sizes[i]
        if i == num_segments - 1:
            e = len(encoded)
        else:
            e += segment_sizes[i + 1]

    return segments


def merge_split_input(segments: List[List[int]], block_size: int) -> List[int]:
    recomposed = segments[0]
    for i in range(1, len(segments)):
        recomposed += segments[i][block_size:]
    return recomposed
