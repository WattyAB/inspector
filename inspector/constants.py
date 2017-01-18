from __future__ import print_function, division

LINEWIDTH = 1.1
DATA_ALPHA = 0.80
SPAN_ALPHA = 0.3
AXISBG = 'white'
BACKGROUND_COLOR = 'white'
FIG_FACECOLOR = 'white'
XTICK_ROTATION = 6
CLEANED = 'cleaned'
FRACTION_PRESHOWN = 6

MINIMUM_Y_RANGE = 10  # TODO make dynamic and less contraining

DEFAULT_GAP_LIMIT = 20

class Labels(object):
    BFILL = 'bfill'
    FFILL = 'ffill'
    DISCARD = 'discard'
    ZERO = 'zero'
    GOOD = 'good'
    COMMENT = 'comment'
    LINEAR_FILL = 'linear-fill'


LABEL_COLOR_MAP = {
    Labels.BFILL: 'darkviolet',
    Labels.FFILL: 'salmon',
    Labels.DISCARD: 'orange',
    Labels.ZERO: 'steelblue',
    Labels.GOOD: 'green',
    Labels.LINEAR_FILL: 'hotpink',
    Labels.COMMENT: 'darkseagreen',
}


COLORNAMES = ['aliceblue', 'antiquewhite', 'aqua', 'aquamarine', 'azure',
'beige', 'bisque', 'black', 'blanchedalmond', 'blue', 'blueviolet', 'brown',
'burlywood', 'cadetblue', 'chartreuse', 'chocolate', 'coral', 'cornflowerblue',
'cornsilk', 'crimson', 'cyan', 'darkblue', 'darkcyan', 'darkgoldenrod',
'darkgray', 'darkgreen', 'darkgrey', 'darkkhaki', 'darkmagenta', 'darkolivegreen',
'lavenderblush', 'lawngreen', 'lemonchiffon', 'lightblue', 'lightcoral',
'lightcyan', 'lightgoldenrodyellow', 'lightgray', 'lightgreen', 'lightgrey',
'lightpink', 'lightsalmon', 'lightseagreen', 'lightskyblue', 'lightslategray',
'lightslategrey', 'lightsteelblue', 'lightyellow', 'lime', 'limegreen', 'linen',
'magenta', 'maroon', 'mediumaquamarine', 'mediumblue', 'mediumorchid',
'mediumpurple', 'mediumseagreen', 'mediumslateblue', 'mediumspringgreen',
'mediumturquoise', 'mediumvioletred', 'midnightblue', 'mintcream', 'mistyrose',
'moccasin', 'navajowhite', 'navy', 'oldlace', 'olive', 'olivedrab', 'orange',
'orangered', 'orchid', 'palegoldenrod', 'palegreen', 'paleturquoise',
'palevioletred', 'papayawhip', 'peachpuff', 'peru', 'pink', 'plum', 'powderblue',
'purple', 'red', 'rosybrown', 'royalblue', 'saddlebrown', 'salmon', 'sandybrown',
'seagreen', 'seashell', 'sienna', 'silver', 'skyblue', 'slateblue', 'slategray',
'slategrey', 'snow', 'springgreen', 'steelblue', 'tan', 'teal', 'thistle',
'tomato', 'turquoise', 'violet', 'wheat', 'yellow', 'yellowgreen']

OTHER_NICE_SEPARATED_COLORS = [
'#0000FF',
'#FF0000',
'#00FF00',
'#00002B',
'#FF1AB8',
'#FFD300',
'#005300',
'#8182FC',
'#A14A43',
'#00FFC2',
'#008395',
'#00007B',
'#95D34F',
'#F69EDB',
'#D311FF',
'#7B1A69',
'#F61160',
'#FFC183',
'#2323X8',
'#8CA77B',
'#837200',
'#72F6FF',
'#9EC1FF',
'#715F79']

_NOT_FUNCTIONING = ['b', 'g', 'r', 'c', 'm', 'y', 'grey']

# color reference: https://en.wikipedia.org/wiki/Web_colors#X11_color_names
# Plot command to visualize:
#     plt.imshow(
#         np.repeat(
#             np.array([map(lambda c: QColor(c).getRgbF(), COLORS[:25])]),
#             25,
#             axis=0
#         ),
#         interpolation='none'
#     )
# TODO: fix that existing color are not reused when removing some series, and adding some new
COLORS = [
    'blue', 'red', 'forestgreen',
    'magenta', 'darkorange', 'teal',
    'deeppink', 'navy', 'dodgerblue',
    'turquoise', 'darkviolet', 'darkRed',
    'lime', 'gold', 'steelblue',
    'cyan', 'darkGreen', 'olive',
    'black',
    # --- end of good colors ---
    'peru', 'darkslategray', 'darkBlue',
    'rosybrown',
    'darkseagreen', 'indigo',
    'hotpink', 'salmon', 'orange',
    'fuchsia', 'purple', 'goldenrod',
    'darkslateblue', 'deepskyblue', 'dimgray', 'greenyellow',
    'darkseagreen', 'firebrick', 'forestgreen', 'gainsboro',
    'honeydew', 'indianred', 'ivory', 'khaki', 'lavender',
    'palevioletred', 'plum', 'powderblue',
    'royalblue', 'saddlebrown', 'sandybrown',
    'seagreen', 'seashell', 'sienna', 'silver', 'skyblue', 'slateblue',
] + COLORNAMES[::-1]*3  # Let's not run out of colors

