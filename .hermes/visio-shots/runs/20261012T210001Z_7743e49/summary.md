# Visio shots 20261012T210001Z_7743e49

Candidate 7743e49 on `feat/layout-phase-4`; cases from `tools/diagram_cases.py` (9103dee); against `9274fff` (9274fff); Visio 16.0 build 20430; 150 dpi.

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
| every_kind | same | 24 differences | - |
| node_outlines | same | same | - |
| groups_and_lanes | same | 20 differences | - |
| group_heading_top_down | same | same | - |
| labels_groups_lanes | same | 27 differences | - |
| two_pages/page 1 | same | same | - |
| two_pages/page 2 | same | same | - |
| hub5 | same | same | - |
| hub5_top_down | same | same | - |
| chain25 | same | 46 differences | - |
| lanes3 | same | 19 differences | - |
| fanin | same | same | - |
| pins | same | same | - |

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
- the page: width=11.26in height=7.22in viewBox=0 0 810.72 519.84 -> width=11.15in height=7.22in viewBox=0 0 802.8 519.84
- shape 2 moved (+0.600 in, +0.000 in): translate(304.56,-383.04) -> translate(347.76,-383.04)
- shape 3 moved (-0.110 in, +0.000 in): translate(586.8,-368.64) -> translate(578.88,-368.64)
- shape 4 moved (-0.110 in, +0.000 in): translate(601.2,-216.72) -> translate(593.28,-216.72)
- shape 5 moved (+0.600 in, +0.000 in): translate(318.96,-176.4) -> translate(362.16,-176.4)
- shape 6 moved (+0.600 in, +0.000 in): translate(87.84,-172.8) -> translate(131.04,-172.8)
- shape 7 moved (+0.600 in, +0.000 in): translate(87.84,-61.2) -> translate(131.04,-61.2)
- shape 8 moved (+0.600 in, +0.000 in): translate(318.96,-57.6) -> translate(362.16,-57.6)
- shape 9 moved (+0.600 in, +0.000 in): translate(506.88,-64.8) -> translate(550.08,-64.8)
- shape 10 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 11 moved (+0.600 in, +0.000 in): translate(462.96,-415.44) -> translate(506.16,-415.44)
- shape 11 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 12 moved (-0.410 in, +0.000 in): translate(673.2,-281.52) -> translate(643.68,-281.52)
- shape 12 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-0 use transform=scale(-4.36,-4.36)  xlink:hre...
- shape 13 moved (+0.600 in, +0.000 in): translate(477.36,-228.96) -> translate(520.56,-228.96)
- shape 13 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 14 moved (+0.600 in, +0.000 in): translate(246.24,-208.8) -> translate(289.44,-208.8)
- shape 15 moved (+0.600 in, +0.000 in): translate(167.04,-126) -> translate(210.24,-126)
- shape 16 moved (+0.600 in, +0.000 in): translate(246.24,-93.6) -> translate(289.44,-93.6)
- shape 17 moved (+0.600 in, +0.000 in): translate(434.16,-93.6) -> translate(477.36,-93.6)
- shape 18 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-0 use transform=scale(-4.36,-4.36)  xlink:hre... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-0 use transform=scale(-4.36,-4.36)  xlink:hre...
- shape 19 moved (-0.110 in, +0.000 in): translate(275.04,-290.88) -> translate(267.12,-290.88)
- shape 20 moved (-0.110 in, +0.000 in): translate(579.6,-256.32) -> translate(571.68,-256.32)
- shape 21 moved (-0.340 in, +0.000 in): translate(601.2,-285.12) -> translate(576.72,-285.12)

## node_outlines

node_outlines: a decision, a rounded node and two data stores (one tall) each with three edges at offset points; every line and arrowhead must touch the drawn outline

## groups_and_lanes

groups_and_lanes: three lanes, a group holding a group; every shape where it was written

ref -> candidate, after recalc:
- the page: width=20.25in height=9.59in viewBox=0 0 1458 690.48 -> width=20.72in height=9.59in viewBox=0 0 1491.84 690.48
- shape 2 drawn differently: rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:1.25} height=632.2 width=1422 x=0 y=58.2803 -> rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:1.25} height=632.2 width=1455.84 x=0 y=58.2803
- shape 3 drawn differently: path style={fill:#fff9f1;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:1.25} d=M0 690.48 L1422 690.48 L1422 662.13 L0 662.13 L0 690.48 Z -> path style={fill:#fff9f1;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:1.25} d=M0 690.48 L1455.84 690.48 L1455.84 662.13 L0 662.13 L0 690.48 Z
- shape 4 drawn differently: rect style={fill:none} height=589.68 width=1422 x=0 y=100.8 -> rect style={fill:none} height=589.68 width=1455.84 x=0 y=100.8
- shape 8 drawn differently: rect style={fill:#fff9f1;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.24} height=14.1732 width=1422 x=0 y=676.307 -> rect style={fill:#fff9f1;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.24} height=14.1732 width=1455.84 x=0 y=676.307
- shape 10 drawn differently: rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=141.12 width=1422 x=0 y=549.36 -> rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=141.12 width=1455.84 x=0 y=549.36
- shape 13 drawn differently: rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=307.44 width=1422 x=0 y=383.04 -> rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=307.44 width=1455.84 x=0 y=383.04
- shape 16 drawn differently: rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=141.12 width=1422 x=0 y=549.36 -> rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=141.12 width=1455.84 x=0 y=549.36
- shape 18 moved (+0.470 in, +0.000 in): translate(519.84,-192.96) -> translate(553.68,-192.96)
- shape 19 moved (+0.470 in, +0.000 in): translate(768.96,-211.68) -> translate(802.8,-211.68)
- shape 22 moved (+0.470 in, +0.000 in): translate(555.84,-396) -> translate(589.68,-396)
- shape 23 moved (+0.470 in, +0.000 in): translate(786.96,-229.68) -> translate(820.8,-229.68)
- shape 24 moved (+0.470 in, +0.000 in): translate(1018.08,-229.68) -> translate(1051.92,-229.68)
- shape 25 moved (+0.470 in, +0.000 in): translate(1249.2,-88.56) -> translate(1283.04,-88.56)
- shape 27 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 28 moved (+0.470 in, +0.000 in): translate(635.04,-262.08) -> translate(668.88,-262.08)
- shape 29 moved (+0.470 in, +0.000 in): translate(945.36,-262.08) -> translate(979.2,-262.08)
- shape 30 moved (+0.470 in, +0.000 in): translate(1097.28,-120.96) -> translate(1131.12,-120.96)
- shape 31 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 32 moved (+0.040 in, +0.000 in): translate(762.48,-558.72) -> translate(765.36,-558.72)

## group_heading_top_down

group_heading_top_down: a top-down edge into a grouped node, whose one-line heading must stay clear of the connector; every shape where it was written

## labels_groups_lanes

labels_groups_lanes: labels inside lanes, parallel labelled edges, a label into a headed group, a label wider than its gap; every shape where it was written

ref -> candidate, after recalc:
- the page: width=21.81in height=9.17in viewBox=0 0 1570.32 660.24 -> width=23.41in height=9.17in viewBox=0 0 1685.52 660.24
- shape 2 drawn differently: rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:1.25} height=601.96 width=1534.32 x=0 y=58.2803 -> rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:1.25} height=601.96 width=1649.52 x=0 y=58.2803
- shape 3 drawn differently: path style={fill:#fff9f1;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:1.25} d=M0 660.24 L1534.32 660.24 L1534.32 631.89 L0 631.89 L0 660.24 Z -> path style={fill:#fff9f1;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:1.25} d=M0 660.24 L1649.52 660.24 L1649.52 631.89 L0 631.89 L0 660.24 Z
- shape 4 drawn differently: rect style={fill:none} height=559.44 width=1534.32 x=0 y=100.8 -> rect style={fill:none} height=559.44 width=1649.52 x=0 y=100.8
- shape 8 drawn differently: rect style={fill:#fff9f1;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.24} height=14.1732 width=1534.32 x=0 y=646.067 -> rect style={fill:#fff9f1;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.24} height=14.1732 width=1649.52 x=0 y=646.067
- shape 10 drawn differently: rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=177.12 width=1534.32 x=0 y=483.12 -> rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=177.12 width=1649.52 x=0 y=483.12
- shape 13 drawn differently: rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=274.32 width=1534.32 x=0 y=385.92 -> rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=274.32 width=1649.52 x=0 y=385.92
- shape 16 drawn differently: rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=108 width=1534.32 x=0 y=552.24 -> rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=108 width=1649.52 x=0 y=552.24
- shape 18 moved (+1.200 in, +0.000 in): translate(743.76,-162) -> translate(830.16,-162)
- shape 20 moved (+0.800 in, +0.000 in): translate(410.4,-523.44) -> translate(468,-523.44)
- shape 21 moved (+1.200 in, +0.000 in): translate(761.76,-180) -> translate(848.16,-180)
- shape 22 moved (+1.200 in, +0.000 in): translate(992.88,-346.32) -> translate(1079.28,-346.32)
- shape 23 moved (+1.600 in, +0.000 in): translate(1361.52,-72) -> translate(1476.72,-72)
- shape 24 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 25 moved (-0.480 in, +0.000 in): translate(307.44,-559.44) -> translate(272.88,-559.44)
- shape 26 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 27 moved (+0.740 in, +0.000 in): translate(268.56,-545.04) -> translate(321.84,-545.04)
- shape 28 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 29 moved (+0.540 in, +0.000 in): translate(331.92,-530.64) -> translate(370.8,-530.64)
- shape 30 moved (+0.800 in, +0.000 in): translate(489.6,-212.4) -> translate(547.2,-212.4)
- shape 30 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 31 moved (+0.800 in, +1.610 in): translate(396.72,-357.12) -> translate(454.32,-473.04)
- shape 32 moved (+1.200 in, +0.000 in): translate(920.16,-212.4) -> translate(1006.56,-212.4)
- shape 32 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 33 moved (+1.200 in, +0.000 in): translate(1072.08,-104.4) -> translate(1158.48,-104.4)
- shape 33 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 34 moved (+0.690 in, +0.000 in): translate(1115.28,-93.6) -> translate(1164.96,-93.6)

## two_pages/page 1

two_pages: two pages and a page link; every shape on both pages where it was written

## two_pages/page 2

two_pages: two pages and a page link; every shape on both pages where it was written

## hub5

hub5: a hub with five children, two feeding one target; every shape where it was written

## hub5_top_down

hub5_top_down: the same hub laid out top down; every shape where it was written

## chain25

chain25: a 25 step chain, two decisions that skip a step, one feedback edge; every shape where it was written

ref -> candidate, after recalc:
- the page: width=16.86in height=11.12in viewBox=0 0 1213.92 800.64 -> width=17.56in height=11.12in viewBox=0 0 1264.32 800.64
- shape 1 moved (+0.700 in, +0.000 in): translate(94.32,-678.24) -> translate(144.72,-678.24)
- shape 2 moved (+0.700 in, +0.000 in): translate(325.44,-678.24) -> translate(375.84,-678.24)
- shape 3 moved (+0.700 in, +0.000 in): translate(556.56,-678.24) -> translate(606.96,-678.24)
- shape 4 moved (+0.700 in, +0.000 in): translate(787.68,-678.24) -> translate(838.08,-678.24)
- shape 5 moved (+0.700 in, +0.000 in): translate(1018.8,-678.24) -> translate(1069.2,-678.24)
- shape 6 moved (+0.700 in, +0.000 in): translate(1018.8,-555.84) -> translate(1069.2,-555.84)
- shape 7 moved (+0.700 in, +0.000 in): translate(787.68,-555.84) -> translate(838.08,-555.84)
- shape 8 moved (+0.700 in, +0.000 in): translate(527.76,-541.44) -> translate(578.16,-541.44)
- shape 9 moved (+0.350 in, +0.000 in): translate(296.64,-570.24) -> translate(321.84,-570.24)
- shape 10 moved (+0.350 in, +0.000 in): translate(65.52,-475.92) -> translate(90.72,-475.92)
- shape 11 moved (+0.350 in, +0.000 in): translate(65.52,-367.92) -> translate(90.72,-367.92)
- shape 12 moved (+0.350 in, +0.000 in): translate(296.64,-367.92) -> translate(321.84,-367.92)
- shape 13 moved (+0.350 in, +0.000 in): translate(527.76,-367.92) -> translate(552.96,-367.92)
- shape 14 moved (+0.350 in, +0.000 in): translate(758.88,-367.92) -> translate(784.08,-367.92)
- shape 15 moved (+0.350 in, +0.000 in): translate(990,-367.92) -> translate(1015.2,-367.92)
- shape 16 moved (+0.350 in, +0.000 in): translate(990,-245.52) -> translate(1015.2,-245.52)
- shape 17 moved (+0.350 in, +0.000 in): translate(730.08,-231.12) -> translate(755.28,-231.12)
- shape 26 moved (+0.350 in, +0.000 in): translate(296.64,-475.92) -> translate(321.84,-475.92)
- shape 28 moved (+0.700 in, +0.000 in): translate(252.72,-710.64) -> translate(303.12,-710.64)
- shape 29 moved (+0.700 in, +0.000 in): translate(483.84,-710.64) -> translate(534.24,-710.64)
- shape 30 moved (+0.700 in, +0.000 in): translate(714.96,-710.64) -> translate(765.36,-710.64)
- shape 31 moved (+0.700 in, +0.000 in): translate(946.08,-710.64) -> translate(996.48,-710.64)
- shape 32 moved (+0.700 in, +0.000 in): translate(1098,-620.64) -> translate(1148.4,-620.64)
- shape 33 moved (+0.700 in, +0.000 in): translate(946.08,-588.24) -> translate(996.48,-588.24)
- shape 34 moved (+0.700 in, +0.000 in): translate(714.96,-588.24) -> translate(765.36,-588.24)
- shape 35 moved (+0.350 in, +0.000 in): translate(455.04,-602.64) -> translate(480.24,-602.64)
- shape 35 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 36 moved (+0.880 in, +0.000 in): translate(467.28,-591.84) -> translate(530.64,-591.84)
- shape 37 moved (+0.350 in, +0.000 in): translate(455.04,-508.32) -> translate(480.24,-508.32)
- shape 37 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 38 moved (+0.930 in, +0.510 in): translate(472.32,-533.52) -> translate(539.28,-570.24)
- shape 39 moved (+0.350 in, +0.000 in): translate(223.92,-501.12) -> translate(249.12,-501.12)
- shape 40 moved (+0.350 in, +0.000 in): translate(223.92,-515.52) -> translate(249.12,-515.52)
- shape 41 moved (+0.350 in, +0.000 in): translate(144.72,-432.72) -> translate(169.92,-432.72)
- shape 42 moved (+0.350 in, +0.000 in): translate(223.92,-400.32) -> translate(249.12,-400.32)
- shape 43 moved (+0.350 in, +0.000 in): translate(455.04,-400.32) -> translate(480.24,-400.32)
- shape 44 moved (+0.350 in, +0.000 in): translate(686.16,-400.32) -> translate(711.36,-400.32)
- shape 45 moved (+0.350 in, +0.000 in): translate(917.28,-400.32) -> translate(942.48,-400.32)
- shape 46 moved (+0.350 in, +0.000 in): translate(1062,-310.32) -> translate(1087.2,-310.32)
- shape 47 moved (+0.350 in, +0.000 in): translate(917.28,-277.92) -> translate(942.48,-277.92)
- shape 48 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 49 moved (+0.520 in, +0.000 in): translate(670.32,-281.52) -> translate(707.76,-281.52)
- shape 50 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 51 moved (+0.590 in, +0.500 in): translate(673.92,-223.92) -> translate(716.4,-259.92)
- shape 60 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...

## lanes3

lanes3: three lanes, a decision that splits into two lanes and rejoins; every shape where it was written

ref -> candidate, after recalc:
- the page: width=23.81in height=6.62in viewBox=0 0 1714.32 476.64 -> width=24.41in height=6.62in viewBox=0 0 1757.52 476.64
- shape 2 drawn differently: rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:1.25} height=418.36 width=1678.32 x=0 y=58.2803 -> rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:1.25} height=418.36 width=1721.52 x=0 y=58.2803
- shape 3 drawn differently: path style={fill:#fff9f1;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:1.25} d=M0 476.64 L1678.32 476.64 L1678.32 448.29 L0 448.29 L0 476.64 Z -> path style={fill:#fff9f1;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:1.25} d=M0 476.64 L1721.52 476.64 L1721.52 448.29 L0 448.29 L0 476.64 Z
- shape 4 drawn differently: rect style={fill:none} height=375.84 width=1678.32 x=0 y=100.8 -> rect style={fill:none} height=375.84 width=1721.52 x=0 y=100.8
- shape 8 drawn differently: rect style={fill:#fff9f1;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.24} height=14.1732 width=1678.32 x=0 y=462.467 -> rect style={fill:#fff9f1;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.24} height=14.1732 width=1721.52 x=0 y=462.467
- shape 10 drawn differently: rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=108 width=1678.32 x=0 y=368.64 -> rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=108 width=1721.52 x=0 y=368.64
- shape 13 drawn differently: rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=159.84 width=1678.32 x=0 y=316.8 -> rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=159.84 width=1721.52 x=0 y=316.8
- shape 16 drawn differently: rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=108 width=1678.32 x=0 y=368.64 -> rect style={fill:none;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=108 width=1721.52 x=0 y=368.64
- shape 22 moved (+0.600 in, +0.000 in): translate(1057.68,-72) -> translate(1100.88,-72)
- shape 23 moved (+0.600 in, +0.000 in): translate(1057.68,-203.04) -> translate(1100.88,-203.04)
- shape 24 moved (+0.600 in, +0.000 in): translate(1288.8,-72) -> translate(1332,-72)
- shape 25 moved (+0.600 in, +0.000 in): translate(1519.92,-75.6) -> translate(1563.12,-75.6)
- shape 29 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 30 moved (-1.330 in, +1.220 in): translate(916.56,-93.6) -> translate(820.8,-181.44)
- shape 31 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 32 moved (-0.050 in, +0.000 in): translate(963.36,-224.64) -> translate(959.76,-224.64)
- shape 33 moved (+0.600 in, +0.000 in): translate(1216.08,-136.8) -> translate(1259.28,-136.8)
- shape 34 moved (+0.600 in, +0.000 in): translate(1216.08,-104.4) -> translate(1259.28,-104.4)
- shape 35 moved (+0.600 in, +0.000 in): translate(1447.2,-104.4) -> translate(1490.4,-104.4)

## fanin

fanin: four sources into one target; every shape where it was written

## pins

pins: a diamond whose first and last boxes share a row and whose last is pinned to layer 3; every shape where it was written
