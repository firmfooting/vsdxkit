# Visio shots 20261012T213409Z_1f96911

Candidate 1f96911 on `feat/layout-phase-6` with uncommitted changes; cases from `tools/diagram_cases.py` (ca3e609); against `c051321` (c051321); Visio 16.0 build 20430; 150 dpi.

| Case | Candidate on open vs after recalc | Ref vs candidate | Before vs candidate |
|---|---|---|---|
| copy_style_clash | same | same | - |
| copy_style_absent | same | same | - |
| swimlanes | same | same | - |
| lanes_kinds | same | same | - |
| lanes_one | same | same | - |
| lanes_two | same | same | - |
| lanes_title | same | 1 difference | - |
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
| every_kind | same | same | - |
| node_outlines | same | same | - |
| groups_and_lanes | same | 1 difference | - |
| group_heading_top_down | same | same | - |
| labels_groups_lanes | same | 1 difference | - |
| two_pages/page 1 | same | same | - |
| two_pages/page 2 | same | same | - |
| hub5 | same | same | - |
| hub5_top_down | same | same | - |
| chain25 | same | same | - |
| lanes3 | same | 1 difference | - |
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

## lanes_title

lanes_title: two laned steps built by the builder, the title bar reading the page name; every shape where it was written

ref -> candidate, after recalc:
- shape 3 drawn differently: text style={fill:#000000;font-family:Calibri;font-size:1.33333em} x=4 y=307.43 "Cross-Functional Flowchart" -> text style={fill:#000000;font-family:Calibri;font-size:1.33333em} x=4 y=307.43 "Intake and review"

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

## node_outlines

node_outlines: a decision, a rounded node and two data stores (one tall) each with three edges at offset points; every line and arrowhead must touch the drawn outline

## groups_and_lanes

groups_and_lanes: three lanes, a group holding a group; every shape where it was written

ref -> candidate, after recalc:
- shape 3 drawn differently: text style={fill:#000000;font-family:Calibri;font-size:1.33333em} x=4 y=681.11 "Cross-Functional Flowchart" -> text style={fill:#000000;font-family:Calibri;font-size:1.33333em} x=4 y=681.11 "Lanes"

## group_heading_top_down

group_heading_top_down: a top-down edge into a grouped node, whose one-line heading must stay clear of the connector; every shape where it was written

## labels_groups_lanes

labels_groups_lanes: labels inside lanes, parallel labelled edges, a label into a headed group, a label wider than its gap; every shape where it was written

ref -> candidate, after recalc:
- shape 3 drawn differently: text style={fill:#000000;font-family:Calibri;font-size:1.33333em} x=4 y=650.87 "Cross-Functional Flowchart" -> text style={fill:#000000;font-family:Calibri;font-size:1.33333em} x=4 y=650.87 "Labels"

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

## lanes3

lanes3: three lanes, a decision that splits into two lanes and rejoins; every shape where it was written

ref -> candidate, after recalc:
- shape 3 drawn differently: text style={fill:#000000;font-family:Calibri;font-size:1.33333em} x=4 y=467.27 "Cross-Functional Flowchart" -> text style={fill:#000000;font-family:Calibri;font-size:1.33333em} x=4 y=467.27 "lanes3"

## fanin

fanin: four sources into one target; every shape where it was written

## pins

pins: a diamond whose first and last boxes share a row and whose last is pinned to layer 3; every shape where it was written
