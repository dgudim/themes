import sys
from textwrap import wrap

gruvbox_colors = ["ebdbb2", "cc241d", "98971a", "d79921", "458588", "b16286", "689d6a", "a89984", "282828", "928374", "fb4934", "b8bb26", "fabd2f", "83a598", "d3869b", "8ec07c", "ebdbb2"]

source_colors = []
matched_colors = []

theme = str(sys.argv[1])
theme_file = open(theme, "rt")
theme_file_out = open(theme + "_gruv", "wt")
start = False
color = ""

def is_hex(char):
    return (char >= '0' and char <= '9') or (char >= 'a' and char <= 'f') or (char >= 'A' and char <= 'F')

def diff(color1, color2):
    red1 = 0
    green1 = 0
    blue1 = 0

    if len(color) == 6:
        red1 = int(color1[0:2], 16)
        green1 = int(color1[2:4], 16)
        blue1 = int(color1[4:6], 16)
    else:
        red1 = int(color1[0] + color1[0], 16)
        green1 = int(color1[1] + color1[1], 16)
        blue1 = int(color1[2] + color1[2], 16)

    return abs(red1 - int(color2[:2], 16)) + abs(green1 - int(color2[2:4], 16)) + abs(blue1 - int(color2[4:6], 16));

def find_closest_color(color):
    best_color = ""
    mindiff = 100000000000000

    currdif = 0
    for gruv_color in gruvbox_colors:
        currdif = diff(color, gruv_color)
        if currdif < mindiff:
            mindiff = currdif
            best_color = gruv_color
    return best_color


matched_color_curr = ""
for char in theme_file.read():
    if start and is_hex(char):
        color += char
    elif start:
        start = False
        if len(color) == 6 or len(color) == 3:
            matched_color_curr = find_closest_color(color)
            source_colors.append(color)
            matched_colors.append(matched_color_curr)
            print(color + " --> " + matched_color_curr)
        color = ""
    if char == '#':
        start = True

theme_file.seek(0)
for line in theme_file:
    for i in range(0, len(source_colors)):
        if source_colors[i] in line:
            line = line.replace(source_colors[i], matched_colors[i])
            break
    theme_file_out.write(line)

theme_file.close()

