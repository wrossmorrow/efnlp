#!/bin/bash
G=1000000
mkdir -p results
for B in 1 2 3 4 5 7 10 12 15 20 30; do
	printf "\nB = $B\n"
	poetry run python -m efnlp -c data/tinywillspeare.txt \
		-L test/unit/data/shakes.json \
		-s -m -b $B -g $G -o results/$B.txt
done

exit

# scratch pad

poetry run python -m efnlp -c data/tinywillspeare.txt -b 10 -g 1000000 -o tmp/rust.txt
