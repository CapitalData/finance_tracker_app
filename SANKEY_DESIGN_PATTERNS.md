# Sankey Diagram Design Patterns: Preserving Path Continuity

## Problem Statement

In multi-hop financial flows (e.g., Worker → Broker/ACD → Client), intermediate nodes (like ACD as a broker) can obscure the natural continuity of a single transaction path. When visualizing:

```
Worker → ACD → BHanalytics
```

The visual continuity is lost because ACD appears as a separate node, making it unclear that this represents a single unified path from the original worker to the final destination.

## Design Solutions

### 1. Color Links by Source Node (RECOMMENDED - Currently Best)

**Description:**
- Assign each source node (worker) a unique color
- All links originating from that source maintain that color throughout their entire path
- Even links that pass through intermediate brokers retain the source color

**Visual Effect:**
```
Worker A (Red) → ACD → BHanalytics   [All links in RED]
Worker B (Blue) → ACD → BHanalytics  [All links in BLUE]
```

**Advantages:**
- ✅ Preserves complete path continuity visually
- ✅ Shows which worker initiated the flow
- ✅ Clean and intuitive
- ✅ Minimal code changes
- ✅ Works with any number of hops
- ✅ Scalable to large datasets

**Disadvantages:**
- ❌ Limited color palette (max ~20 distinct colors before repetition)
- ❌ May be confusing if multiple workers have similar roles
- ❌ Doesn't highlight the destination

**Implementation Complexity:**
```python
# Pseudo-code
for each link:
    link.color = color_of_source_node
```

**Best For:** Tracking origin-based flows (which worker/entity started this path)

---

### 2. Color Links by Destination Node

**Description:**
- Assign colors based on the final destination node
- All intermediate hops show the destination's color
- Emphasizes where flows ultimately go

**Visual Effect:**
```
Worker A → ACD → BHanalytics (Green)  [All links in GREEN]
Worker B → ACD → BHanalytics (Green)  [All links in GREEN]
Worker A → ACD → Netflix (Purple)     [All links in PURPLE]
```

**Advantages:**
- ✅ Shows final destination clearly
- ✅ Groups related flows visually
- ✅ Good for understanding end-to-end outcomes

**Disadvantages:**
- ❌ Loses information about which worker originated the flow
- ❌ Can appear monotonous if many paths go to same destination
- ❌ Requires data about final destinations in each row

**Best For:** Understanding outcome-based patterns (where is money going)

---

### 3. Color Links by Source-Destination Pair

**Description:**
- Create unique colors for each source-to-destination combination
- Links from Worker A to BHanalytics get one color
- Links from Worker B to BHanalytics get a different color
- All intermediate hops preserve the pair's color

**Visual Effect:**
```
Worker A → ACD → BHanalytics (Red)    [All in RED]
Worker B → ACD → BHanalytics (Blue)   [All in BLUE]
Worker A → ACD → Netflix (Green)      [All in GREEN]
```

**Advantages:**
- ✅ Most information-rich coloring
- ✅ Shows both origin and destination
- ✅ Preserves complete path context
- ✅ No limit on number of flows (unlimited combinations)

**Disadvantages:**
- ❌ Can appear cluttered with many colors
- ❌ Harder to distinguish similar paths
- ❌ May require a legend (not standard in Plotly Sankey)
- ❌ Requires preprocessing to identify final destination

**Implementation Complexity:**
```python
# Pseudo-code
for each link:
    source_name = nodes[link.source]
    target_name = nodes[link.target]
    final_dest = get_final_destination(link.data)
    link.color = get_color_for_pair(source_name, final_dest)
```

**Best For:** Complex multi-level flows requiring maximum detail

---

### 4. Gradient Colors (Source Color → Destination Color)

**Description:**
- Links transition in color from source to destination
- Shows both origin and destination with a visual gradient
- Intermediate nodes show the transition

**Visual Effect:**
```
Worker A (Red) → ACD (transitioning) → BHanalytics (Blue)
[Link gradually shifts from RED to BLUE]
```

**Advantages:**
- ✅ Aesthetically striking
- ✅ Shows both origin and destination
- ✅ Very intuitive visual representation

**Disadvantages:**
- ❌ Complex to implement (requires SVG gradients)
- ❌ May be difficult to interpret in complex diagrams
- ❌ Performance implications for large datasets
- ❌ Requires detailed link styling (not native Plotly Sankey)

**Implementation Complexity:**
Very high - requires custom SVG manipulation or custom visualization library

**Best For:** Premium visualizations / executive presentations

---

### 5. Enhanced Hover Tooltips (Information-Based)

**Description:**
- Keep links a single color (by status, amount, etc.)
- Add detailed tooltip showing the complete path
- Hover reveals: "Worker A → ACD → BHanalytics → [Final Outcome]"

**Visual Effect:**
```
Default view: Simple colors based on status (Paid/Pending)
On hover: "Path: Acme Corp → ACD Broker → BHanalytics → Paid"
```

**Advantages:**
- ✅ Preserves clean diagram appearance
- ✅ No color limit issues
- ✅ Provides full context on demand
- ✅ Easy to implement
- ✅ Works with existing Sankey
- ✅ Can show calculation details

**Disadvantages:**
- ❌ Information hidden until hover
- ❌ Difficult for presentations/static exports
- ❌ Not visible in printed/screenshot contexts

**Implementation Example:**
```python
hovertemplate = (
    '<b>Path:</b> %{customdata[0]}<br>'
    '<b>Amount:</b> $%{value:,.2f}<br>'
    '<b>Status:</b> %{customdata[1]}<br>'
    '<extra></extra>'
)
```

**Best For:** Interactive dashboards where users explore data

---

### 6. Hybrid Approach: Color by Source + Enhanced Tooltips

**Description (RECOMMENDED FOR YOUR USE CASE):**
- Color all links by source node (preserves path continuity)
- Add detailed hover tooltips showing:
  - Complete path
  - Final destination
  - Flow amount
  - Transaction status

**Visual Effect:**
```
Default: Worker A flows are RED, Worker B flows are BLUE
Hover on any RED flow: "Worker A → ACD → BHanalytics | $50,000 | Paid"
```

**Advantages:**
- ✅ Maximum clarity of path continuity
- ✅ Shows both origin and destination
- ✅ Clean default view
- ✅ Rich information on demand
- ✅ Practical for your data
- ✅ Works with existing node filters
- ✅ Scalable to any number of paths

**Disadvantages:**
- ⚠️ Requires preprocessing to add final destination to each row
- ⚠️ Tooltip design becomes more complex

**Implementation Complexity:** Medium - moderate preprocessing needed

**Best For:** Financial flow tracking (YOUR USE CASE)

---

## Recommendation for ACD Finance Tracker

### Primary: Hybrid Approach (Option 6)

**Why this works for your data:**

1. **Workers as sources** - Each worker's flows should be visually tracked through ACD broker to final destination
2. **Path clarity** - Red flows are always Worker A's, Blue is Worker B's, etc.
3. **Rich context** - Hovering shows "Worker A → ACD → BHanalytics → Invoice INV-2401 → $50K Paid"
4. **Scalable** - Works with 5 workers or 500 workers
5. **Clean interface** - Doesn't clutter the diagram with excessive colors

### Implementation Steps

1. **Add final destination column** to each dataset during preprocessing
2. **Assign source colors** based on worker/entity
3. **Color all links by source** (maintaining the color through intermediate nodes)
4. **Enhance tooltip** with complete path information

### Example Data Structure

```python
# Original
Source: "Worker A"
Target: "ACD"
Status: "Paid"

# Becomes
Source: "Worker A"
Target: "ACD"
FinalDestination: "BHanalytics"  # NEW
Status: "Paid"
Invoice: "INV-2401"               # NEW for tooltip
Amount: 50000

# Tooltip shows:
# "Worker A → ACD → BHanalytics | Invoice INV-2401 | $50,000 | Paid"
```

---

## Implementation Code Example

```python
# 1. Assign source colors
source_colors = {}
color_palette = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4', '#FFEAA7', '#DFE6E9']

for idx, node in enumerate(unique_nodes):
    if node in source_entities:  # workers, companies that initiate flows
        source_colors[node] = color_palette[idx % len(color_palette)]

# 2. Color links by source
link_colors = []
for source_idx in source_indices:
    source_node = unique_nodes[source_idx]
    link_colors.append(source_colors.get(source_node, '#CCCCCC'))

# 3. Enhance tooltip
link_dict = dict(
    source=source_indices,
    target=target_indices,
    value=demo_data['Amount'],
    color=link_colors,
    customdata=list(zip(
        demo_data['FinalDestination'],
        demo_data['Status'],
        demo_data['Invoice'],
        demo_data['Amount']
    )),
    hovertemplate=(
        '<b>%{source.label}</b> → <b>%{target.label}</b> → '
        '<b>%{customdata[0]}</b><br>'
        'Invoice: %{customdata[2]}<br>'
        'Amount: $%{customdata[3]:,.2f}<br>'
        'Status: %{customdata[1]}<extra></extra>'
    )
)
```

---

## Comparison Matrix

| Feature | Option 1 | Option 2 | Option 3 | Option 4 | Option 5 | Option 6 |
|---------|----------|----------|----------|----------|----------|----------|
| **Path Continuity** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Shows Origin** | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Shows Destination** | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Implementation** | Easy | Easy | Medium | Hard | Easy | Medium |
| **Scalability** | Excellent | Good | Good | Fair | Excellent | Excellent |
| **Clean UI** | Yes | Yes | No | Yes | Yes | Yes |
| **Works w/ Filters** | Yes | Yes | Yes | Yes | Yes | Yes |

---

## Decision Tree

```
Are you tracking origin-based flows?
    YES → Use Option 1 (Color by Source)
    NO → Next question

Do you have final destination data?
    YES → Do you want maximum detail?
        YES → Use Option 3 (Color by Pair) or Option 6 (Hybrid)
        NO → Use Option 5 (Enhanced Tooltips)
    NO → Use Option 1 (Color by Source) + add final destination during preprocessing

Is this for interactive exploration?
    YES → Use Option 6 (Hybrid: Color + Tooltips)
    NO → Is this for presentation?
        YES → Use Option 4 (Gradient)
        NO → Use Option 1 or 5
```

---

## Conclusion

For the **ACD Finance Tracker**, the **Hybrid Approach (Option 6)** is recommended because:

1. ✅ Tracks worker-initiated flows through broker to final destination
2. ✅ Maintains visual path continuity with source-based coloring
3. ✅ Provides rich context via hover tooltips
4. ✅ Scales well with your data volume
5. ✅ Integrates with existing node filters
6. ✅ Works for both interactive and static use cases

This approach balances **visual clarity** with **information richness** without adding complexity to the node structure.

