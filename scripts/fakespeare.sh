#!/bin/bash
mkdir -p results
for B in 1 2 3 4 5 7 10 12 15 20 ; do
	printf "\nB = $B\n"
	python -m efnlp -c data/tinywillspeare.txt -m -b $B -g 10000 -o results/$B.txt
done
