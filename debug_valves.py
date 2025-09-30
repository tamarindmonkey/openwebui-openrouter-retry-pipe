#!/usr/bin/env python3
"""
Debug script to check valve values in openrouter-retry.py
"""

# Read and execute the pipe file to get the Pipe class
with open('openrouter-retry.py', 'r') as f:
    pipe_code = f.read()

# Extract just the class definitions and imports we need
import_lines = []
class_lines = []
in_class = False

for line in pipe_code.split('\n'):
    if line.startswith('import ') or line.startswith('from ') or line.startswith('try:') or line.startswith('except'):
        import_lines.append(line)
    elif line.startswith('class Pipe:'):
        in_class = True
        class_lines.append(line)
    elif in_class:
        class_lines.append(line)
        if line.startswith('    pass') and len([l for l in class_lines[-10:] if 'class ' in l]) >= 2:
            break

# Execute the imports and class definition
exec('\n'.join(import_lines + class_lines))

# Create pipe instance
pipe = Pipe()

print("Pipe valves:")
for key, value in pipe.valves.__dict__.items():
    print(f"  {key}: {value} (type: {type(value)})")

print("\nDefault ENABLE_NOTIFICATIONS:", getattr(pipe.valves, "ENABLE_NOTIFICATIONS", "NOT_FOUND"))
print("Has ENABLE_NOTIFICATIONS attr:", hasattr(pipe.valves, "ENABLE_NOTIFICATIONS"))