import io
s = io.open('retrieval_mutants.py', 'r', encoding='utf-8', newline='').read()
i = s.index('PREDICTIONS = {')
j = s.index('LEVERS = [')
print(repr(s[j - 420:j]))
