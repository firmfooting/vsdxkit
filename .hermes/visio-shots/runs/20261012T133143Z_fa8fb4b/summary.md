# Visio shots 20261012T133143Z_fa8fb4b

Candidate fa8fb4b on `feat/layout-phase2-ports` with uncommitted changes; cases from `tools/diagram_cases.py` (9ae524a); against `ae14536` (ae14536); Visio 16.0 build 20430; 150 dpi.

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
| every_kind | same | 11 differences | - |
| node_outlines | same | 18 differences | - |
| groups_and_lanes | same | 11 differences | - |
| group_heading_top_down | same | same | - |
| labels_groups_lanes | same | 10 differences | - |
| two_pages/page 1 | same | same | - |
| two_pages/page 2 | same | same | - |
| hub5 | same | 29 differences | - |
| hub5_top_down | same | 27 differences | - |
| chain25 | same | 24 differences | - |
| lanes3 | same | 12 differences | - |
| fanin | same | 7 differences | - |

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
- shape 10 moved (+0.000 in, +0.080 in): translate(180.72,-397.44) -> translate(180.72,-403.2)
- shape 10 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 12 moved (-0.050 in, +0.000 in): translate(676.8,-281.52) -> translate(673.2,-281.52)
- shape 12 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 13 moved (+0.000 in, +0.100 in): translate(477.36,-231.12) -> translate(477.36,-238.32)
- shape 13 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 18 moved (+0.000 in, -0.050 in): translate(180.72,-223.92) -> translate(180.72,-220.32)
- shape 18 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-0 use transform=scale(-4.36,-4.36)  xlink:hre... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-0 use transform=scale(-4.36,-4.36)  xlink:hre...
- shape 20 moved (+0.000 in, +0.050 in): translate(579.6,-252.72) -> translate(579.6,-256.32)
- shape 20 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 21 moved (+0.020 in, +0.000 in): translate(599.76,-285.12) -> translate(601.2,-285.12)

## node_outlines

node_outlines: a decision, a rounded node and two data stores (one tall) each with three edges at offset points; every line and arrowhead must touch the drawn outline

ref -> candidate, after recalc:
- shape 7 moved (+0.000 in, +0.100 in): translate(195.12,-238.32) -> translate(195.12,-245.52)
- shape 7 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 9 moved (+0.000 in, -0.100 in): translate(195.12,-223.92) -> translate(195.12,-216.72)
- shape 9 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 10 moved (-0.200 in, +0.100 in): translate(440.64,-238.32) -> translate(426.24,-245.52)
- shape 10 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 12 moved (-0.200 in, -0.100 in): translate(440.64,-223.92) -> translate(426.24,-216.72)
- shape 12 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 13 moved (-0.100 in, +0.000 in): translate(592.56,-131.76) -> translate(585.36,-131.76)
- shape 15 moved (+0.100 in, +0.000 in): translate(606.96,-131.76) -> translate(614.16,-131.76)
- shape 16 moved (-0.040 in, +0.100 in): translate(447.12,-106.56) -> translate(444.24,-113.76)
- shape 16 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 18 moved (-0.040 in, -0.100 in): translate(447.12,-92.16) -> translate(444.24,-84.96)
- shape 18 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 19 moved (-0.020 in, +0.100 in): translate(216.72,-106.56) -> translate(215.28,-113.76)
- shape 19 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 21 moved (-0.020 in, -0.100 in): translate(216.72,-92.16) -> translate(215.28,-84.96)
- shape 21 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...

## groups_and_lanes

groups_and_lanes: three lanes, a group holding a group; every shape where it was written

ref -> candidate, after recalc:
- shape 27 moved (-1.100 in, +0.000 in): translate(483.12,-428.4) -> translate(403.92,-428.4)
- shape 27 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 28 moved (-1.100 in, +0.000 in): translate(714.24,-262.08) -> translate(635.04,-262.08)
- shape 28 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 29 moved (+0.000 in, +0.050 in): translate(945.36,-258.48) -> translate(945.36,-262.08)
- shape 29 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 30 moved (-1.100 in, +0.000 in): translate(1176.48,-120.96) -> translate(1097.28,-120.96)
- shape 30 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 31 moved (+0.000 in, +1.070 in): translate(483.12,-217.44) -> translate(483.12,-294.48)
- shape 31 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-0 use transform=scale(-4.36,-4.36)  xlink:hre... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 32 moved (+4.250 in, +2.090 in): translate(456.48,-408.24) -> translate(762.48,-558.72)

## group_heading_top_down

group_heading_top_down: a top-down edge into a grouped node, whose one-line heading must stay clear of the connector; every shape where it was written

## labels_groups_lanes

labels_groups_lanes: labels inside lanes, parallel labelled edges, a label into a headed group, a label wider than its gap; every shape where it was written

ref -> candidate, after recalc:
- shape 24 moved (+0.000 in, +0.100 in): translate(252,-563.04) -> translate(252,-570.24)
- shape 25 moved (+0.000 in, +0.100 in): translate(307.44,-552.24) -> translate(307.44,-559.44)
- shape 28 moved (+0.000 in, -0.100 in): translate(252,-548.64) -> translate(252,-541.44)
- shape 29 moved (+0.000 in, -1.380 in): translate(298.8,-583.92) -> translate(298.8,-484.56)
- shape 30 moved (-1.100 in, +0.000 in): translate(568.8,-212.4) -> translate(489.6,-212.4)
- shape 30 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 31 moved (-2.440 in, -0.230 in): translate(572.4,-373.68) -> translate(396.72,-357.12)
- shape 33 moved (-1.100 in, +0.000 in): translate(1151.28,-104.4) -> translate(1072.08,-104.4)
- shape 33 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 34 moved (-0.550 in, -1.910 in): translate(1154.88,-231.12) -> translate(1115.28,-93.6)

## two_pages/page 1

two_pages: two pages and a page link; every shape on both pages where it was written

## two_pages/page 2

two_pages: two pages and a page link; every shape on both pages where it was written

## hub5

hub5: a hub with five children, two feeding one target; every shape where it was written

ref -> candidate, after recalc:
- the page: width=9.42in height=7.14in viewBox=0 0 678.24 514.08 -> width=13.64in height=6in viewBox=0 0 982.08 432
- shape 1 moved (+5.220 in, +1.480 in): translate(36,-224.64) -> translate(411.84,-331.2)
- shape 1 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=449.28 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=367.2; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=63.94 y=485.28 "Intake" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=63.94 y=403.2 "Intake"
- shape 2 moved (-3.210 in, -3.240 in): translate(267.12,-413.28) -> translate(36,-180)
- shape 2 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=449.28 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=367.2; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=62.54 y=485.28 "Child 1" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=62.54 y=403.2 "Child 1"
- shape 3 moved (-0.600 in, -1.930 in): translate(267.12,-318.96) -> translate(223.92,-180)
- shape 3 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=449.28 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=367.2; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=62.54 y=485.28 "Child 2" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=62.54 y=403.2 "Child 2"
- shape 4 moved (+4.620 in, +0.690 in): translate(267.12,-130.32) -> translate(599.76,-180)
- shape 4 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=449.28 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=367.2; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=62.54 y=485.28 "Child 3" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=62.54 y=403.2 "Child 3"
- shape 5 moved (+2.010 in, -0.620 in): translate(267.12,-224.64) -> translate(411.84,-180)
- shape 5 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=449.28 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=367.2; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=62.54 y=485.28 "Child 4" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=62.54 y=403.2 "Child 4"
- shape 6 moved (+7.230 in, +2.000 in): translate(267.12,-36) -> translate(787.68,-180)
- shape 6 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=449.28 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=367.2; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=62.54 y=485.28 "Child 5" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=62.54 y=403.2 "Child 5"
- shape 7 moved (-1.100 in, -2.670 in): translate(498.24,-228.24) -> translate(419.04,-36)
- shape 7 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=57.6 rx=18 ry=18 width=144 x=0 y=456.48 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=57.6 rx=18 ry=18 width=144 x=0 y=374.4; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=53.67 y=488.88 "Archive" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=53.67 y=406.8 "Archive"
- shape 8 moved (-1.100 in, -0.370 in): translate(194.4,-271.44) -> translate(115.2,-244.8)
- shape 8 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 9 moved (+1.510 in, -0.270 in): translate(194.4,-264.24) -> translate(303.12,-244.8)
- shape 9 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 10 moved (+5.220 in, +1.140 in): translate(194.4,-162.72) -> translate(570.24,-244.8)
- shape 10 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 11 moved (+4.120 in, -0.170 in): translate(194.4,-257.04) -> translate(491.04,-244.8)
- shape 11 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 12 moved (+5.220 in, +2.450 in): translate(194.4,-68.4) -> translate(570.24,-244.8)
- shape 12 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 13 moved (-1.700 in, -2.720 in): translate(425.52,-260.64) -> translate(303.12,-64.8)
- shape 13 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 14 moved (+0.910 in, -2.220 in): translate(425.52,-253.44) -> translate(491.04,-93.6)
- shape 14 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...

## hub5_top_down

hub5_top_down: the same hub laid out top down; every shape where it was written

ref -> candidate, after recalc:
- the page: width=13.64in height=5.62in viewBox=0 0 982.08 404.64 -> width=13.64in height=6in viewBox=0 0 982.08 432
- shape 1 moved (+0.000 in, +0.380 in): translate(411.84,-303.84) -> translate(411.84,-331.2)
- shape 1 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=339.84 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=367.2; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=63.94 y=375.84 "Intake" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=63.94 y=403.2 "Intake"
- shape 2 moved (+0.000 in, +0.190 in): translate(36,-166.32) -> translate(36,-180)
- shape 2 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=339.84 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=367.2; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=62.54 y=375.84 "Child 1" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=62.54 y=403.2 "Child 1"
- shape 3 moved (+0.000 in, +0.190 in): translate(223.92,-166.32) -> translate(223.92,-180)
- shape 3 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=339.84 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=367.2; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=62.54 y=375.84 "Child 2" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=62.54 y=403.2 "Child 2"
- shape 4 moved (+0.000 in, +0.190 in): translate(599.76,-166.32) -> translate(599.76,-180)
- shape 4 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=339.84 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=367.2; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=62.54 y=375.84 "Child 3" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=62.54 y=403.2 "Child 3"
- shape 5 moved (+0.000 in, +0.190 in): translate(411.84,-166.32) -> translate(411.84,-180)
- shape 5 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=339.84 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=367.2; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=62.54 y=375.84 "Child 4" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=62.54 y=403.2 "Child 4"
- shape 6 moved (+0.000 in, +0.190 in): translate(787.68,-166.32) -> translate(787.68,-180)
- shape 6 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=339.84 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=64.8 width=158.4 x=0 y=367.2; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=62.54 y=375.84 "Child 5" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=62.54 y=403.2 "Child 5"
- shape 7 drawn differently: rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=57.6 rx=18 ry=18 width=144 x=0 y=347.04 -> rect style={fill:#ffffff;stroke:#000000;stroke-linecap:round;stroke-linejoin:round;stroke-width:0.75} height=57.6 rx=18 ry=18 width=144 x=0 y=374.4; text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=53.67 y=379.44 "Archive" -> text style={fill:#000000;font-family:Calibri;font-size:1.00001em} x=53.67 y=406.8 "Archive"
- shape 8 moved (+0.000 in, +0.190 in): translate(115.2,-231.12) -> translate(115.2,-244.8)
- shape 8 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 9 moved (+0.000 in, +0.190 in): translate(303.12,-231.12) -> translate(303.12,-244.8)
- shape 9 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 10 moved (+1.000 in, +0.190 in): translate(498.24,-231.12) -> translate(570.24,-244.8)
- shape 10 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 11 moved (+0.000 in, +0.190 in): translate(491.04,-231.12) -> translate(491.04,-244.8)
- shape 11 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 12 moved (+0.900 in, +0.190 in): translate(505.44,-231.12) -> translate(570.24,-244.8)
- shape 12 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 13 moved (+0.000 in, -0.400 in): translate(303.12,-93.6) -> translate(303.12,-64.8)
- shape 13 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 14 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...

## chain25

chain25: a 25 step chain, two decisions that skip a step, one feedback edge; every shape where it was written

ref -> candidate, after recalc:
- shape 35 moved (+0.000 in, +0.380 in): translate(1090.8,-539.28) -> translate(1090.8,-566.64)
- shape 35 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 36 moved (+0.180 in, -0.220 in): translate(1090.8,-571.68) -> translate(1103.76,-555.84)
- shape 37 moved (+0.000 in, +0.230 in): translate(1090.8,-488.16) -> translate(1090.8,-504.72)
- shape 37 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 38 moved (-0.160 in, -0.380 in): translate(1119.6,-521.28) -> translate(1108.08,-493.92)
- shape 39 moved (+0.000 in, +0.330 in): translate(859.68,-488.16) -> translate(859.68,-511.92)
- shape 39 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 40 moved (+0.000 in, +0.280 in): translate(859.68,-539.28) -> translate(859.68,-559.44)
- shape 40 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 45 moved (+0.000 in, +0.100 in): translate(628.56,-314.64) -> translate(628.56,-321.84)
- shape 45 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 48 moved (-0.760 in, +0.380 in): translate(1343.52,-336.24) -> translate(1288.8,-363.6)
- shape 48 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 49 moved (-0.130 in, -0.230 in): translate(1372.32,-369.36) -> translate(1362.96,-352.8)
- shape 50 moved (-0.740 in, +0.230 in): translate(1343.52,-285.84) -> translate(1290.24,-302.4)
- shape 50 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 51 moved (+0.000 in, -0.070 in): translate(1367.28,-296.64) -> translate(1367.28,-291.6)
- shape 53 moved (+0.000 in, +0.050 in): translate(1581.84,-137.52) -> translate(1581.84,-141.12)
- shape 53 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-0 use transform=scale(-4.36,-4.36)  xlink:hre... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-0 use transform=scale(-4.36,-4.36)  xlink:hre...
- shape 54 moved (+0.000 in, +0.100 in): translate(1350.72,-115.92) -> translate(1350.72,-123.12)
- shape 54 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 60 moved (+0.000 in, -0.050 in): translate(628.56,-108.72) -> translate(628.56,-105.12)
- shape 60 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...

## lanes3

lanes3: three lanes, a decision that splits into two lanes and rejoins; every shape where it was written

ref -> candidate, after recalc:
- shape 27 moved (-1.100 in, +0.000 in): translate(468.72,-249.84) -> translate(389.52,-249.84)
- shape 27 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 29 moved (-1.200 in, +0.000 in): translate(952.56,-104.4) -> translate(866.16,-104.4)
- shape 29 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 30 moved (-0.880 in, -0.990 in): translate(979.92,-164.88) -> translate(916.56,-93.6)
- shape 31 moved (+0.100 in, +0.000 in): translate(952.56,-249.84) -> translate(959.76,-249.84)
- shape 31 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 32 moved (-0.230 in, -0.640 in): translate(979.92,-285.12) -> translate(963.36,-239.04)
- shape 33 moved (+0.000 in, +0.400 in): translate(1216.08,-108) -> translate(1216.08,-136.8)
- shape 33 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 34 moved (+0.000 in, +0.050 in): translate(1216.08,-100.8) -> translate(1216.08,-104.4)
- shape 34 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...

## fanin

fanin: four sources into one target; every shape where it was written

ref -> candidate, after recalc:
- shape 7 moved (+0.000 in, +0.300 in): translate(194.4,-220.32) -> translate(194.4,-241.92)
- shape 7 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 8 moved (+0.000 in, +0.280 in): translate(194.4,-213.12) -> translate(194.4,-233.28)
- shape 8 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 9 moved (+0.000 in, +0.330 in): translate(194.4,-162.72) -> translate(194.4,-186.48)
- shape 9 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
- shape 10 drawn differently: path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink... -> path style={marker-end:url({marker style={fill:#000000;fill-opacity:1;stroke:#000000;stroke-opacity:1;stroke-width:0.22935779816514} markerUnits=strokeWidth orient=auto overflow=visible refX=-13.08 use transform=scale(-4.36,-4.36)  xlink...
