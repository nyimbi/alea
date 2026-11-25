"""Count characters of each '### ... (max N characters)' answer in an application file."""
import re, sys

def main(path: str) -> int:
	text = open(path, encoding="utf-8").read()
	i = text.find("## Form answers")
	assert i >= 0, "no '## Form answers' section"
	bad = 0
	for m in re.finditer(r"^### (.+?)\n(.*?)(?=^### |\Z)", text[i:], re.S | re.M):
		head, body = m.group(1), m.group(2).strip()
		lim = re.search(r"max\.? ?([\d ,]+) characters", head)
		if not lim:
			continue
		n = int(re.sub(r"\D", "", lim.group(1)))
		flag = "OK " if len(body) <= n else "OVER"
		bad += len(body) > n
		print(f"{flag} {len(body):5d}/{n:5d}  {head}")
	return 1 if bad else 0

if __name__ == "__main__":
	sys.exit(main(sys.argv[1]))
