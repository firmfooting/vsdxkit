# Visio shots 20260927T124443Z_9f38454

Candidate 9f38454 on `test/visio-shots`; cases from `tools/writes_land_cases.py` (acda876); against `main` (e7ad0aa); Visio 16.0 build 20326; 150 dpi.

| Case | Candidate on open vs after recalc | Ref vs candidate | Before vs candidate |
|---|---|---|---|
| 01_colours | same | 1 difference | 1 difference |
| 01b_text_colour | same | 1 difference | 1 difference |
| 02_guarded | **STALE ON OPEN**, 1 difference | 2 differences | 2 differences |
| 02b_prop_over_formula | same | same | same |
| 02c_instance_geometry | same | 1 difference | 2 differences |
| 03_glued_end | **STALE ON OPEN**, 2 differences | 2 differences | 2 differences |
| 03b_instance_property | same | same | 4 differences |
| 04_moved_instance | same | 1 difference | 1 difference |
| 05_plain_line_text | same | 2 differences | 2 differences |
| 05b_diagonal_line_text | same | 2 differences | 2 differences |
| 06_diagonals | same | same | 4 differences |

**FAIL**: 2 reason(s)
- 02_guarded is stale on open
- 03_glued_end is stale on open

## 01_colours

01_colours: shape 37, the title bar, has a red line, a green fill and blue text

ref on open -> after recalc:
- shape 37 drawn differently: path style={fill:#00ff00;stroke:#ff0000;stroke-linecap:butt;stroke-width:1.25} d=M0 595.28 L785.2 595.28 L785.2 566.93 L0 566.93 L0 595.28 Z -> path style={fill:#fff9f1;stroke:#d49f00;stroke-linecap:butt;stroke-width:1.25} d=M0 595.28 L785.2 595.28 L785.2 566.93 L0 566.93 L0 595.28 Z

ref -> candidate, after recalc:
- shape 37 drawn differently: path style={fill:#fff9f1;stroke:#d49f00;stroke-linecap:butt;stroke-width:1.25} d=M0 595.28 L785.2 595.28 L785.2 566.93 L0 566.93 L0 595.28 Z -> path style={fill:#00ff00;stroke:#ff0000;stroke-linecap:butt;stroke-width:1.25} d=M0 595.28 L785.2 595.28 L785.2 566.93 L0 566.93 L0 595.28 Z

before -> candidate, after recalc:
- shape 37 drawn differently: path style={fill:#fff9f1;stroke:#d49f00;stroke-linecap:butt;stroke-width:1.25} d=M0 595.28 L785.2 595.28 L785.2 566.93 L0 566.93 L0 595.28 Z -> path style={fill:#00ff00;stroke:#ff0000;stroke-linecap:butt;stroke-width:1.25} d=M0 595.28 L785.2 595.28 L785.2 566.93 L0 566.93 L0 595.28 Z; text style={fill:#000000;font-family:Calibri;font-size:1.33333em} x=4 y=585.9 "Cross-Functional Flowchart" -> text style={fill:#0000ff;font-family:Calibri;font-size:1.33333em} x=4 y=585.9 "Cross-Functional Flowchart"

## 01b_text_colour

01b_text_colour: shape 2's text is blue

ref on open -> after recalc:
- shape 2 drawn differently: text style={fill:#0000ff;font-family:Calibri;font-size:1.00001em} x=53.08 y=788.8 "Text Color" -> text style={fill:#ff0000;font-family:Calibri;font-size:1.00001em} x=53.08 y=788.8 "Text Color"

ref -> candidate, after recalc:
- shape 2 drawn differently: text style={fill:#ff0000;font-family:Calibri;font-size:1.00001em} x=53.08 y=788.8 "Text Color" -> text style={fill:#0000ff;font-family:Calibri;font-size:1.00001em} x=53.08 y=788.8 "Text Color"

before -> candidate, after recalc:
- shape 2 drawn differently: text style={fill:#ff0000;font-family:Calibri;font-size:1.00001em} x=53.08 y=788.8 "Text Color" -> text style={fill:#0000ff;font-family:Calibri;font-size:1.00001em} x=53.08 y=788.8 "Text Color"

## 02_guarded

02_guarded: shape 1 is 2.5 in wide with its pin at x = 3.0 in

candidate on open -> after recalc:
- shape 1 moved (-0.167 in, +0.000 in): translate(138.047,-710.504) -> translate(126,-710.504)

ref on open -> after recalc:
- shape 1 moved (-1.417 in, +0.000 in): translate(138.047,-710.504) -> translate(36,-710.504)
- shape 1 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=113.386 width=180 x=0 y=728.504 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=113.386 width=72 x=0 y=728.504; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=63.2 y=788.8 "Shape Text" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=9.2 y=788.8 "Shape Text"

ref -> candidate, after recalc:
- shape 1 moved (+1.250 in, +0.000 in): translate(36,-710.504) -> translate(126,-710.504)
- shape 1 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=113.386 width=72 x=0 y=728.504 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=113.386 width=180 x=0 y=728.504; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=9.2 y=788.8 "Shape Text" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=63.2 y=788.8 "Shape Text"

before -> candidate, after recalc:
- shape 1 moved (+1.500 in, +0.000 in): translate(18,-710.504) -> translate(126,-710.504)
- shape 1 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=113.386 width=155.906 x=0 y=728.504 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=113.386 width=180 x=0 y=728.504; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=51.16 y=788.8 "Shape Text" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=63.2 y=788.8 "Shape Text"

## 02b_prop_over_formula

02b_prop_over_formula: shape 54's Function property reads Sales, not its swimlane's heading

## 02c_instance_geometry

02c_instance_geometry: 'Conn A' starts its path at x = 0.25 in; its copy, the same master's instance, still at 0

ref -> candidate, after recalc:
- shape 4 drawn differently: path style={stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} d=M18 841.89 L255.12 785.2 -> path style={stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} d=M0 841.89 L255.12 785.2

before -> candidate, after recalc:
- shape 3 drawn differently: path style={stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} d=M0 841.89 L255.12 785.2 -> path style={stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} d=M18 841.89 L255.12 785.2
- shape 4 only in the second drawing

## 03_glued_end

03_glued_end: connector 6's begin is free, 1 in left of where it was; its end is still glued to shape 2

candidate on open -> after recalc:
- shape 6 moved (-1.000 in, +0.000 in): translate(173.906,-760.11) -> translate(101.906,-760.11)
- shape 6 drawn differently: path style={stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} d=M0 834.8 L45.78 834.8 -> path style={stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} d=M0 834.8 L117.78 834.8

ref -> candidate, after recalc:
- shape 6 moved (-1.000 in, +0.000 in): translate(173.906,-760.11) -> translate(101.906,-760.11)
- shape 6 drawn differently: path style={stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} d=M0 834.8 L45.78 834.8 -> path style={stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} d=M0 834.8 L117.78 834.8

before -> candidate, after recalc:
- shape 6 moved (-1.000 in, +0.000 in): translate(173.906,-760.11) -> translate(101.906,-760.11)
- shape 6 drawn differently: path style={stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} d=M0 834.8 L45.78 834.8 -> path style={stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} d=M0 834.8 L117.78 834.8

## 03b_instance_property

03b_instance_property: shape 7's ShapeClass reads Changed; its copy, the same master's instance, still reads Location

before -> candidate, after recalc:
- shape 15 only in the second drawing
- shape 16 only in the second drawing
- shape 17 only in the second drawing
- shape 18 only in the second drawing

## 04_moved_instance

04_moved_instance: 'Conn A' is drawn between its two ends, 1 in right of and 1 in above where it was

ref on open -> after recalc:
- shape 3 drawn differently: path style={stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} d=M72 769.89 L327.12 713.2 -> path style={stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} d=M0 841.89 L72 769.89 L327.12 713.2 L183.12 857.2; rect style={fill:#ffffff;stroke:none} height=9.59985 width=23.3281 x=115.895 y=808.744 -> rect style={fill:#ffffff;stroke:none} height=9.59985 width=23.3281 x=95.645 y=807.091; text style={fill:#000000;font-family:Calibri;font-size:0.666664em} x=115.89 y=815.94 "Conn A" -> text style={fill:#000000;font-family:Calibri;font-size:0.666664em} x=95.64 y=814.29 "Conn A"

ref -> candidate, after recalc:
- shape 3 drawn differently: path style={stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} d=M0 841.89 L72 769.89 L327.12 713.2 L183.12 857.2 -> path style={stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} d=M0 841.89 L255.12 785.2; rect style={fill:#ffffff;stroke:none} height=9.59985 width=23.3281 x=95.645 y=807.091 -> rect style={fill:#ffffff;stroke:none} height=9.59985 width=23.3281 x=115.895 y=808.744; text style={fill:#000000;font-family:Calibri;font-size:0.666664em} x=95.64 y=814.29 "Conn A" -> text style={fill:#000000;font-family:Calibri;font-size:0.666664em} x=115.89 y=815.94 "Conn A"

before -> candidate, after recalc:
- shape 3 moved (+1.000 in, +1.000 in): translate(28.3465,-623.622) -> translate(100.346,-695.622)

## 05_plain_line_text

05_plain_line_text: shape 5 runs from (1, 7) to (3, 7) with its text at its middle

ref on open -> after recalc:
- shape 5 moved (-0.072 in, +0.000 in): translate(5.1768,-504) -> translate(0.00387868,-504)

ref -> candidate, after recalc:
- shape 5 moved (+1.000 in, +0.000 in): translate(0.00387868,-504) -> translate(72.0039,-504)
- shape 5 drawn differently: rect style={fill:#ffffff;stroke:none} height=8.20596 width=23.1169 x=132.441 y=103.797 -> rect style={fill:#ffffff;stroke:none} height=8.20596 width=23.1169 x=60.4414 y=607.797; text style={fill:#333333;font-family:Arial;font-size:0.666664em;font-weight:bold} x=132.44 y=110 "Line 1" -> text style={fill:#333333;font-family:Arial;font-size:0.666664em;font-weight:bold} x=60.44 y=614 "Line 1"

before -> candidate, after recalc:
- shape 5 moved (-0.759 in, -0.500 in): translate(126.677,-540) -> translate(72.0039,-504)
- shape 5 drawn differently: path style={marker-end:url({marker style={fill:#5e5e5e;fill-opacity:1;stroke:#5e5e5e;stroke-opacity:1;stroke-width:0.26315789473684} markerUnits=strokeWidth orient=auto overflow=visible refX=-7.6 use transform=scale(-3.8,-3.8)  xlink:hre... -> path style={marker-end:url({marker style={fill:#5e5e5e;fill-opacity:1;stroke:#5e5e5e;stroke-opacity:1;stroke-width:0.26315789473684} markerUnits=strokeWidth orient=auto overflow=visible refX=-7.6 use transform=scale(-3.8,-3.8)  xlink:hre...; rect style={fill:#ffffff;stroke:none} height=8.20596 width=23.1169 x=63.9694 y=607.797 -> rect style={fill:#ffffff;stroke:none} height=8.20596 width=23.1169 x=60.4414 y=607.797; text style={fill:#333333;font-family:Arial;font-size:0.666664em;font-weight:bold} x=63.97 y=614 "Line 1" -> text style={fill:#333333;font-family:Arial;font-size:0.666664em;font-weight:bold} x=60.44 y=614 "Line 1"

## 05b_diagonal_line_text

05b_diagonal_line_text: shape 5 runs from (1, 7) to (4, 11), 5 in long, with its pin and its text at its middle

ref on open -> after recalc:
- shape 5 moved (-0.572 in, +0.000 in): translate(5.1768,-504) -> translate(-35.9942,-504)

ref -> candidate, after recalc:
- shape 5 moved (-5.300 in, -3.400 in): translate(-35.9942,-504) -> translate(-417.594,-259.208) rotate(-53.1301)
- shape 5 drawn differently: path style={marker-end:url({marker style={fill:#5e5e5e;fill-opacity:1;stroke:#5e5e5e;stroke-opacity:1;stroke-width:0.26315789473684} markerUnits=strokeWidth orient=auto overflow=visible refX=-7.6 use transform=scale(-3.8,-3.8)  xlink:hre... -> path style={marker-end:url({marker style={fill:#5e5e5e;fill-opacity:1;stroke:#5e5e5e;stroke-opacity:1;stroke-width:0.26315789473684} markerUnits=strokeWidth orient=auto overflow=visible refX=-7.6 use transform=scale(-3.8,-3.8)  xlink:hre...; rect style={fill:#ffffff;stroke:none} height=8.20596 width=23.1169 x=168.441 y=103.797 -> rect style={fill:#ffffff;stroke:none} height=8.20596 width=23.1169 x=168.441 y=607.797; text style={fill:#333333;font-family:Arial;font-size:0.666664em;font-weight:bold} x=168.44 y=110 "Line 1" -> text style={fill:#333333;font-family:Arial;font-size:0.666664em;font-weight:bold} x=168.44 y=614 "Line 1"

before -> candidate, after recalc:
- shape 5 moved (-7.559 in, -3.900 in): translate(126.677,-540) -> translate(-417.594,-259.208) rotate(-53.1301)
- shape 5 drawn differently: path style={marker-end:url({marker style={fill:#5e5e5e;fill-opacity:1;stroke:#5e5e5e;stroke-opacity:1;stroke-width:0.26315789473684} markerUnits=strokeWidth orient=auto overflow=visible refX=-7.6 use transform=scale(-3.8,-3.8)  xlink:hre... -> path style={marker-end:url({marker style={fill:#5e5e5e;fill-opacity:1;stroke:#5e5e5e;stroke-opacity:1;stroke-width:0.26315789473684} markerUnits=strokeWidth orient=auto overflow=visible refX=-7.6 use transform=scale(-3.8,-3.8)  xlink:hre...; rect style={fill:#ffffff;stroke:none} height=8.20596 width=23.1169 x=63.9694 y=607.797 -> rect style={fill:#ffffff;stroke:none} height=8.20596 width=23.1169 x=168.441 y=607.797; text style={fill:#333333;font-family:Arial;font-size:0.666664em;font-weight:bold} x=63.97 y=614 "Line 1" -> text style={fill:#333333;font-family:Arial;font-size:0.666664em;font-weight:bold} x=168.44 y=614 "Line 1"

## 06_diagonals

06_diagonals: 'Conn A' runs from (1, 1) to (3, 2) and 'Line A' from (4, 1) to (5, 3), each drawn between its ends

before -> candidate, after recalc:
- shape 2 moved (-4.316 in, -14.634 in): translate(-154.285,-660.267) rotate(-12.5288) -> translate(-465.009,393.385) rotate(-63.4349)
- shape 2 drawn differently: path style={stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} d=M0 841.89 L261.34 841.89 -> path style={stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} d=M0 841.89 L161 841.89; rect style={fill:#ffffff;stroke:none} height=14.4001 width=29.7307 x=115.806 y=834.69 -> rect style={fill:#ffffff;stroke:none} height=14.4001 width=29.7307 x=65.6331 y=834.69; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=115.81 y=845.49 "Line A" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=65.63 y=845.49 "Line A"
- shape 3 moved (+0.606 in, -7.661 in): translate(28.3465,-623.622) -> translate(72,-72)
- shape 3 drawn differently: path style={stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} d=M0 841.89 L255.12 785.2 -> path style={stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} d=M0 841.89 L144 769.89; rect style={fill:#ffffff;stroke:none} height=9.59985 width=23.3281 x=115.895 y=808.744 -> rect style={fill:#ffffff;stroke:none} height=9.59985 width=23.3281 x=60.3359 y=801.09; text style={fill:#000000;font-family:Calibri;font-size:0.666664em} x=115.89 y=815.94 "Conn A" -> text style={fill:#000000;font-family:Calibri;font-size:0.666664em} x=60.34 y=808.29 "Conn A"
