#!/bin/bash
G=1000000
mkdir -p results
for B in 1 2 3 4 5 7 10 12 15 20 ; do
	printf "\nB = $B\n"
	poetry run python -m efnlp -c data/tinywillspeare.txt \
		-b $B -g $G -o tmp/$B.txt
done
