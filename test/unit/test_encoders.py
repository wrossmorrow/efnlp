import pytest  # noqa: F401

from os.path import dirname
from random import choices

import efnlp


def test_encoder_1() -> None:

	D = {"aaa": 0, "aab": 1, "aa": 2, "a": 3, "b": 4}
	E = efnlp.EncoderSet.from_dict(D)
	assert E.dict() == D

	# all the declared strings match declared tokens
	for p, t in D.items():
		assert E.encode(p) == [t], (p, t, E.encode(p))

	# invalid character raises in strict mode
	with pytest.raises(ValueError):
		E.encode("c")

	# decoding encoded strings is a no-op
	for _ in range(10):
		s = ''.join(choices(["a","b"], k=100))
		assert E.decode(E.encode(s)) == s

	# non-strict mode ignores unknown characters
	for _ in range(10):
		s = ''.join(choices(["a","b","c"], k=100))
		r = ''.join([c for c in s if c != "c"])
		assert E.decode(E.encode(s, strict=False)) == r


def test_encoder_gpt2() -> None:

	with open(f"{dirname(__file__)}/data/gpt-2.json", "r") as f:
		E = efnlp.EncoderSet.from_json(f.read())
		Ps = E.encodables()

		print(len(Ps))

		for _ in range(10):
			s = u''.join(choices(Ps, k=100))
			assert E.decode(E.encode(s)) == s