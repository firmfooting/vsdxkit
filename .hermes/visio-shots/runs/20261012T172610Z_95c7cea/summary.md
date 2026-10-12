# Visio shots 20261012T172610Z_95c7cea

Candidate 95c7cea on `feat/layout-phase-3` with uncommitted changes; cases from `tools/diagram_cases.py` (9103dee); against `88294c4` (88294c4); Visio 16.0 build 20430; 150 dpi.

| Case | Candidate on open vs after recalc | Ref vs candidate | Before vs candidate |
|---|---|---|---|
| copy_style_clash | same | same | - |
| copy_style_absent | same | same | - |
| swimlanes | same | same | - |
| lanes_kinds | same | same | - |
| lanes_one | same | same | - |
| lanes_two | same | same | - |
| lanes_four | same | same | - |
| lanes_extremes | same | same | - |
| lanes_five | same | same | - |
| lanes_uneven | same | same | - |
| lanes_style_clash | same | same | - |
| lanes_style_absent | same | same | - |
| lanes_add | same | same | - |
| lanes_wide | same | same | - |
| lanes_wide_60_3 | same | same | - |
| lanes_wide_60_5 | same | same | - |
| every_kind | same | 10 differences | - |
| node_outlines | same | 10 differences | - |
| groups_and_lanes | same | same | - |
| group_heading_top_down | same | same | - |
| labels_groups_lanes | same | same | - |
| two_pages/page 1 | same | same | - |
| two_pages/page 2 | same | 3 differences | - |
| hub5 | same | 5 differences | - |
| hub5_top_down | same | 5 differences | - |
| chain25 | same | 121 differences | - |
| lanes3 | same | 5 differences | - |
| fanin | same | 9 differences | - |
| pins | same | - | - |

ref could not build `<lambda>`: TypeError: Node.__init__() got an unexpected keyword argument 'layer'. Did you mean 'label'?

**PASS**

## copy_style_clash

copy_style_clash: a shape copied from a document whose style 7 is another style; its sub-shapes show the source's line pattern and margins

## copy_style_absent

copy_style_absent: a shape copied into a document with no style 7; its sub-shapes show the source's line pattern and margins

## swimlanes

swimlanes: a three-lane cross-functional flowchart from create_swimlanes, a process in each lane; every shape where it was written

## lanes_kinds

lanes_kinds: sized Start/End, Decision and Process steps in two lanes; every shape where it was written

## lanes_one

lanes_one: a cross-functional flowchart of one lane; every shape where it was written

## lanes_two

lanes_two: two lanes, a process in each; every shape where it was written

## lanes_four

lanes_four: four lanes, one labelled with the widest letters; every shape where it was written

## lanes_extremes

lanes_extremes: a 0.5 inch lane, a 6 inch lane and a 5 inch wide diagram; every shape where it was written

## lanes_five

lanes_five: five lanes, a process in each; every shape where it was written

## lanes_uneven

lanes_uneven: lanes of different heights, three processes in one and none in another; every shape where it was written

## lanes_style_clash

lanes_style_clash: a diagram in a document whose style 7 is another style; the Separator shows Flow Normal's margins

## lanes_style_absent

lanes_style_absent: a diagram in a document with no style 7; the Separator shows Flow Normal's margins

## lanes_add

lanes_add: a created two-lane diagram with a lane added by add_lane; every shape where it was written

## lanes_wide

lanes_wide: a diagram 22 inches wide on a page widened to 24; every shape where it was written

## lanes_wide_60_3

lanes_wide_60_3: three lanes, a diagram 60 inches wide on a page widened to 61; every shape where it was written

## lanes_wide_60_5

lanes_wide_60_5: five lanes, a diagram 60 inches wide on a page widened to 61; every shape where it was written

## every_kind

every_kind: nine node kinds, six edge kinds, a long edge, a self-loop; every shape where it was written

ref -> candidate, after recalc:
- shape 1 moved (+0.000 in, +0.300 in): translate(36.72,-365.04) -> translate(36.72,-386.64)
- shape 5 moved (+0.000 in, -0.260 in): translate(318.96,-195.12) -> translate(318.96,-176.4)
- shape 6 moved (+0.000 in, -0.260 in): translate(87.84,-191.52) -> translate(87.84,-172.8)
- shape 10 moved (+0.000 in, +0.270 in): translate(180.72,-403.2) -> translate(180.72,-422.64)
- shape 13 moved (+0.000 in, -0.130 in): translate(477.36,-238.32) -> translate(477.36,-228.96)
- shape 13 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 14 moved (+0.000 in, -0.260 in): translate(246.24,-227.52) -> translate(246.24,-208.8)
- shape 15 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 18 moved (+0.000 in, -0.260 in): translate(180.72,-220.32) -> translate(180.72,-201.6)
- shape 18 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-0 use transform=scale(-4.36,-4.36)  xlink:hre... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-0 use transform=scale(-4.36,-4.36)  xlink:hre...

## node_outlines

node_outlines: a decision, a rounded node and two data stores (one tall) each with three edges at offset points; every line and arrowhead must touch the drawn outline

ref -> candidate, after recalc:
- shape 3 moved (+0.000 in, -0.250 in): translate(527.76,-202.32) -> translate(527.76,-184.32)
- shape 10 moved (+0.000 in, -0.250 in): translate(426.24,-245.52) -> translate(426.24,-227.52)
- shape 10 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 11 moved (+0.000 in, -0.250 in): translate(455.04,-231.12) -> translate(455.04,-213.12)
- shape 11 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 12 moved (-0.500 in, -0.250 in): translate(426.24,-216.72) -> translate(390.24,-198.72)
- shape 12 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 13 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 14 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 15 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...

## groups_and_lanes

groups_and_lanes: three lanes, a group holding a group; every shape where it was written

## group_heading_top_down

group_heading_top_down: a top-down edge into a grouped node, whose one-line heading must stay clear of the connector; every shape where it was written

## labels_groups_lanes

labels_groups_lanes: labels inside lanes, parallel labelled edges, a label into a headed group, a label wider than its gap; every shape where it was written

## two_pages/page 1

two_pages: two pages and a page link; every shape on both pages where it was written

## two_pages/page 2

two_pages: two pages and a page link; every shape on both pages where it was written

ref -> candidate, after recalc:
- shape 2 moved (+0.000 in, -0.050 in): translate(224.64,-162) -> translate(224.64,-158.4)
- shape 4 moved (+0.000 in, -0.050 in): translate(151.92,-194.4) -> translate(151.92,-190.8)
- shape 5 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...

## hub5

hub5: a hub with five children, two feeding one target; every shape where it was written

ref -> candidate, after recalc:
- shape 7 moved (-2.610 in, +0.000 in): translate(419.04,-36) -> translate(231.12,-36)
- shape 13 moved (+0.000 in, +0.400 in): translate(303.12,-64.8) -> translate(303.12,-93.6)
- shape 13 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 14 moved (-1.610 in, -0.400 in): translate(491.04,-93.6) -> translate(375.12,-64.8)
- shape 14 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...

## hub5_top_down

hub5_top_down: the same hub laid out top down; every shape where it was written

ref -> candidate, after recalc:
- shape 7 moved (-2.610 in, +0.000 in): translate(419.04,-36) -> translate(231.12,-36)
- shape 13 moved (+0.000 in, +0.400 in): translate(303.12,-64.8) -> translate(303.12,-93.6)
- shape 13 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 14 moved (-1.610 in, -0.400 in): translate(491.04,-93.6) -> translate(375.12,-64.8)
- shape 14 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...

## chain25

chain25: a 25 step chain, two decisions that skip a step, one feedback edge; every shape where it was written

ref -> candidate, after recalc:
- the page: width=22.48in height=10.84in viewBox=0 0 1618.56 780.48 -> width=16.86in height=11.12in viewBox=0 0 1213.92 800.64
- shape 1 moved (-2.410 in, +0.280 in): translate(267.84,-658.08) -> translate(94.32,-678.24)
- shape 1 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=63.9 y=751.68 "Step 1" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=63.9 y=771.84 "Step 1"
- shape 2 moved (-2.410 in, +0.280 in): translate(498.96,-658.08) -> translate(325.44,-678.24)
- shape 2 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=63.9 y=751.68 "Step 2" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=63.9 y=771.84 "Step 2"
- shape 3 moved (-2.410 in, +0.280 in): translate(730.08,-658.08) -> translate(556.56,-678.24)
- shape 3 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=63.9 y=751.68 "Step 3" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=63.9 y=771.84 "Step 3"
- shape 4 moved (-2.410 in, +0.280 in): translate(961.2,-658.08) -> translate(787.68,-678.24)
- shape 4 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=63.9 y=751.68 "Step 4" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=63.9 y=771.84 "Step 4"
- shape 5 moved (-2.410 in, +0.280 in): translate(1192.32,-658.08) -> translate(1018.8,-678.24)
- shape 5 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=63.9 y=751.68 "Step 5" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=63.9 y=771.84 "Step 5"
- shape 6 moved (-5.620 in, -1.420 in): translate(1423.44,-658.08) -> translate(1018.8,-555.84)
- shape 6 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=63.9 y=751.68 "Step 6" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=63.9 y=771.84 "Step 6"
- shape 7 moved (-8.830 in, +0.730 in): translate(1423.44,-503.28) -> translate(787.68,-555.84)
- shape 7 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=63.9 y=751.68 "Step 7" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=63.9 y=771.84 "Step 7"
- shape 8 moved (-8.830 in, +0.730 in): translate(1163.52,-488.88) -> translate(527.76,-541.44)
- shape 8 drawn differently: path style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} d=M93.6 686.88 L187.2 733.68 L93.6 780.48 L0 733.68 L93.6 686.88 Z -> path style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} d=M93.6 707.04 L187.2 753.84 L93.6 800.64 L0 753.84 L93.6 707.04 Z; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=78.3 y=737.28 "Step 8" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=78.3 y=757.44 "Step 8"
- shape 9 moved (-8.830 in, +0.280 in): translate(932.4,-550.08) -> translate(296.64,-570.24)
- shape 9 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=63.9 y=751.68 "Step 9" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=63.9 y=771.84 "Step 9"
- shape 10 moved (-8.830 in, -0.380 in): translate(701.28,-503.28) -> translate(65.52,-475.92)
- shape 10 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=751.68 "Step 10" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=771.84 "Step 10"
- shape 11 moved (-5.620 in, -1.880 in): translate(470.16,-503.28) -> translate(65.52,-367.92)
- shape 11 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=751.68 "Step 11" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=771.84 "Step 11"
- shape 12 moved (+0.800 in, -1.880 in): translate(239.04,-503.28) -> translate(296.64,-367.92)
- shape 12 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=751.68 "Step 12" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=771.84 "Step 12"
- shape 13 moved (+4.010 in, +1.240 in): translate(239.04,-278.64) -> translate(527.76,-367.92)
- shape 13 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=751.68 "Step 13" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=771.84 "Step 13"
- shape 14 moved (+4.010 in, +1.240 in): translate(470.16,-278.64) -> translate(758.88,-367.92)
- shape 14 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=751.68 "Step 14" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=771.84 "Step 14"
- shape 15 moved (+4.010 in, +0.940 in): translate(701.28,-300.24) -> translate(990,-367.92)
- shape 15 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=751.68 "Step 15" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=771.84 "Step 15"
- shape 16 moved (+0.800 in, -0.760 in): translate(932.4,-300.24) -> translate(990,-245.52)
- shape 16 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=751.68 "Step 16" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=771.84 "Step 16"
- shape 17 moved (-6.020 in, -0.760 in): translate(1163.52,-285.84) -> translate(730.08,-231.12)
- shape 17 drawn differently: path style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} d=M93.6 686.88 L187.2 733.68 L93.6 780.48 L0 733.68 L93.6 686.88 Z -> path style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} d=M93.6 707.04 L187.2 753.84 L93.6 800.64 L0 753.84 L93.6 707.04 Z; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=75.26 y=737.28 "Step 17" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=75.26 y=757.44 "Step 17"
- shape 18 moved (-12.840 in, -1.220 in): translate(1423.44,-347.76) -> translate(498.96,-259.92)
- shape 18 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=751.68 "Step 18" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=771.84 "Step 18"
- shape 19 moved (-16.050 in, +0.890 in): translate(1423.44,-101.52) -> translate(267.84,-165.6)
- shape 19 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=751.68 "Step 19" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=771.84 "Step 19"
- shape 20 moved (-16.050 in, +1.190 in): translate(1192.32,-79.92) -> translate(36.72,-165.6)
- shape 20 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=751.68 "Step 20" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=771.84 "Step 20"
- shape 21 moved (-12.840 in, -0.310 in): translate(961.2,-79.92) -> translate(36.72,-57.6)
- shape 21 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=751.68 "Step 21" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=771.84 "Step 21"
- shape 22 moved (-6.420 in, -0.310 in): translate(730.08,-79.92) -> translate(267.84,-57.6)
- shape 22 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=751.68 "Step 22" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=771.84 "Step 22"
- shape 23 moved (+0.000 in, -0.310 in): translate(498.96,-79.92) -> translate(498.96,-57.6)
- shape 23 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=751.68 "Step 23" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=771.84 "Step 23"
- shape 24 moved (+6.420 in, -0.310 in): translate(267.84,-79.92) -> translate(730.08,-57.6)
- shape 24 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=751.68 "Step 24" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=771.84 "Step 24"
- shape 25 moved (+12.840 in, -0.310 in): translate(36.72,-79.92) -> translate(961.2,-57.6)
- shape 25 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=751.68 "Step 25" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=60.86 y=771.84 "Step 25"
- shape 26 moved (-8.830 in, +0.280 in): translate(932.4,-455.76) -> translate(296.64,-475.92)
- shape 26 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=64.79 y=751.68 "Skip 8" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=64.79 y=771.84 "Skip 8"
- shape 27 moved (-12.840 in, -1.220 in): translate(1423.44,-253.44) -> translate(498.96,-165.6)
- shape 27 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=715.68 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=735.84; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=61.75 y=751.68 "Skip 17" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=61.75 y=771.84 "Skip 17"
- shape 28 moved (-2.410 in, +0.280 in): translate(426.24,-690.48) -> translate(252.72,-710.64)
- shape 28 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 29 moved (-2.410 in, +0.280 in): translate(657.36,-690.48) -> translate(483.84,-710.64)
- shape 29 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 30 moved (-2.410 in, +0.280 in): translate(888.48,-690.48) -> translate(714.96,-710.64)
- shape 30 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 31 moved (-2.410 in, +0.280 in): translate(1119.6,-690.48) -> translate(946.08,-710.64)
- shape 31 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 32 moved (-3.510 in, -0.970 in): translate(1350.72,-690.48) -> translate(1098,-620.64)
- shape 32 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 33 moved (-7.730 in, +0.280 in): translate(1502.64,-568.08) -> translate(946.08,-588.24)
- shape 33 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 34 moved (-8.830 in, +0.730 in): translate(1350.72,-535.68) -> translate(714.96,-588.24)
- shape 34 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 35 moved (-8.830 in, +0.500 in): translate(1090.8,-566.64) -> translate(455.04,-602.64)
- shape 35 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 36 moved (-8.840 in, +0.500 in): translate(1103.76,-555.84) -> translate(467.28,-591.84)
- shape 36 drawn differently: rect style={fill:none;stroke:none} height=21.6 width=47.52 x=0 y=758.88 -> rect style={fill:none;stroke:none} height=21.6 width=47.52 x=0 y=779.04; rect style={fill:#ffffff;stroke:none} height=14.4001 width=16.5119 x=15.5042 y=762.48 -> rect style={fill:#ffffff;stroke:none} height=14.4001 width=16.5119 x=15.5042 y=782.64; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=15.5 y=773.28 "Yes" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=15.5 y=793.44 "Yes"
- shape 37 moved (-8.830 in, +0.050 in): translate(1090.8,-504.72) -> translate(455.04,-508.32)
- shape 37 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 38 moved (-8.830 in, +0.550 in): translate(1108.08,-493.92) -> translate(472.32,-533.52)
- shape 38 drawn differently: rect style={fill:none;stroke:none} height=21.6 width=38.88 x=0 y=758.88 -> rect style={fill:none;stroke:none} height=21.6 width=38.88 x=0 y=779.04; rect style={fill:#ffffff;stroke:none} height=14.4001 width=14.0743 x=12.403 y=762.48 -> rect style={fill:#ffffff;stroke:none} height=14.4001 width=14.0743 x=12.403 y=782.64; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=12.4 y=773.28 "No" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=12.4 y=793.44 "No"
- shape 39 moved (-8.830 in, -0.150 in): translate(859.68,-511.92) -> translate(223.92,-501.12)
- shape 39 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 40 moved (-8.830 in, -0.610 in): translate(859.68,-559.44) -> translate(223.92,-515.52)
- shape 40 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 41 moved (-6.720 in, -1.430 in): translate(628.56,-535.68) -> translate(144.72,-432.72)
- shape 41 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 42 moved (-2.410 in, -1.880 in): translate(397.44,-535.68) -> translate(223.92,-400.32)
- shape 42 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 43 moved (+1.900 in, +0.790 in): translate(318.24,-343.44) -> translate(455.04,-400.32)
- shape 43 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 44 moved (+4.010 in, +1.240 in): translate(397.44,-311.04) -> translate(686.16,-400.32)
- shape 44 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 45 moved (+4.010 in, +1.090 in): translate(628.56,-321.84) -> translate(917.28,-400.32)
- shape 45 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 46 moved (+2.810 in, -0.310 in): translate(859.68,-332.64) -> translate(1062,-310.32)
- shape 46 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 47 moved (-2.410 in, -0.760 in): translate(1090.8,-332.64) -> translate(917.28,-277.92)
- shape 47 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 48 moved (-8.770 in, -0.990 in): translate(1288.8,-363.6) -> translate(657.36,-292.32)
- shape 48 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 49 moved (-9.620 in, -0.990 in): translate(1362.96,-352.8) -> translate(670.32,-281.52)
- shape 49 drawn differently: rect style={fill:none;stroke:none} height=21.6 width=47.52 x=0 y=758.88 -> rect style={fill:none;stroke:none} height=21.6 width=47.52 x=0 y=779.04; rect style={fill:#ffffff;stroke:none} height=14.4001 width=16.5119 x=15.5042 y=762.48 -> rect style={fill:#ffffff;stroke:none} height=14.4001 width=16.5119 x=15.5042 y=782.64; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=15.5 y=773.28 "Yes" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=15.5 y=793.44 "Yes"
- shape 50 moved (-8.790 in, -1.450 in): translate(1290.24,-302.4) -> translate(657.36,-198)
- shape 50 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 51 moved (-9.630 in, -0.940 in): translate(1367.28,-291.6) -> translate(673.92,-223.92)
- shape 51 drawn differently: rect style={fill:none;stroke:none} height=21.6 width=38.88 x=0 y=758.88 -> rect style={fill:none;stroke:none} height=21.6 width=38.88 x=0 y=779.04; rect style={fill:#ffffff;stroke:none} height=14.4001 width=14.0743 x=12.403 y=762.48 -> rect style={fill:#ffffff;stroke:none} height=14.4001 width=14.0743 x=12.403 y=782.64; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=12.4 y=773.28 "No" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=12.4 y=793.44 "No"
- shape 52 moved (-14.950 in, +0.340 in): translate(1502.64,-166.32) -> translate(426.24,-190.8)
- shape 52 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 53 moved (-16.050 in, +0.890 in): translate(1581.84,-141.12) -> translate(426.24,-205.2)
- shape 53 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-0 use transform=scale(-4.36,-4.36)  xlink:hre... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 54 moved (-16.050 in, +1.040 in): translate(1350.72,-123.12) -> translate(195.12,-198)
- shape 54 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 55 moved (-13.940 in, +0.140 in): translate(1119.6,-112.32) -> translate(115.92,-122.4)
- shape 55 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 56 moved (-9.630 in, -0.310 in): translate(888.48,-112.32) -> translate(195.12,-90)
- shape 56 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 57 moved (-3.210 in, -0.310 in): translate(657.36,-112.32) -> translate(426.24,-90)
- shape 57 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 58 moved (+3.210 in, -0.310 in): translate(426.24,-112.32) -> translate(657.36,-90)
- shape 58 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 59 moved (+9.630 in, -0.310 in): translate(195.12,-112.32) -> translate(888.48,-90)
- shape 59 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 60 moved (-7.120 in, +1.740 in): translate(628.56,-105.12) -> translate(115.92,-230.4)
- shape 60 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...

## lanes3

lanes3: three lanes, a decision that splits into two lanes and rejoins; every shape where it was written

ref -> candidate, after recalc:
- shape 23 moved (+0.000 in, -0.200 in): translate(1057.68,-217.44) -> translate(1057.68,-203.04)
- shape 31 moved (-0.400 in, -0.200 in): translate(959.76,-249.84) -> translate(930.96,-235.44)
- shape 31 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 32 moved (+0.000 in, -0.200 in): translate(963.36,-239.04) -> translate(963.36,-224.64)
- shape 33 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...

## fanin

fanin: four sources into one target; every shape where it was written

ref -> candidate, after recalc:
- shape 5 moved (+0.000 in, +0.660 in): translate(267.12,-177.12) -> translate(267.12,-224.64)
- shape 6 moved (+0.000 in, +0.660 in): translate(498.24,-180.72) -> translate(498.24,-228.24)
- shape 7 moved (+0.000 in, +0.660 in): translate(194.4,-241.92) -> translate(194.4,-289.44)
- shape 7 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 8 moved (+0.000 in, +0.330 in): translate(194.4,-233.28) -> translate(194.4,-257.04)
- shape 9 moved (+0.000 in, -0.330 in): translate(194.4,-186.48) -> translate(194.4,-162.72)
- shape 9 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 10 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 11 moved (+0.000 in, +0.660 in): translate(425.52,-209.52) -> translate(425.52,-257.04)

## pins

pins: a diamond whose first and last boxes share a row and whose last is pinned to layer 3; every shape where it was written
