from pathlib import Path
import pyperclip

def build_tree(folder, prefix="", output=None):
    if output is None:
        output = []

    folder = Path(folder)
    output.append(prefix + folder.name)

    items = sorted(folder.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))

    for i, item in enumerate(items):
        last = i == len(items) - 1

        if last:
            connector = "└── "
            extension = "    "
        else:
            connector = "├── "
            extension = "│   "

        output.append(prefix + connector + item.name)

        if item.is_dir():
            build_tree(item, prefix + extension, output)

    return output


folder = input("Enter folder path: ")

tree = "\n".join(build_tree(folder))

print(tree)

# Copy to clipboard
pyperclip.copy(tree)

print("\nTree copied to clipboard!")