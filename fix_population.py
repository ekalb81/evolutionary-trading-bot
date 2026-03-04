import re

with open('/data/workspace/trading_system/evolution/population.py', 'r') as f:
    text = f.read()

# Add execution_target generation to the genome assembler
def inject_target(match):
    dict_content = match.group(1)
    injection = """
        "execution_target": {
            "instrument": random.choice(["equity", "equity", "options"]),
            "fractional": True,
            "target_dte": random.choice([7, 14, 30, 45, 60]),
            "target_delta": random.choice([0.3, 0.4, 0.5, 0.6, 0.7])
        },"""
    return "{" + injection + dict_content

text = re.sub(r'\{\s*"id": str\(genome_id\),', inject_target, text)

with open('/data/workspace/trading_system/evolution/population.py', 'w') as f:
    f.write(text)
