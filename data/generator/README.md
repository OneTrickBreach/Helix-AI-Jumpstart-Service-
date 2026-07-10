# Manufacturing Synthetic Data Generator

Phase 1 generates deterministic, synthetic Manufacturing SCO inputs. It uses no customer data and does not load the GPU.

## Command

```bash
python data/generator/generate.py --seed SEED --scenario SCENARIO --output-dir data/generated/SCENARIO/
```

From the repo, prefer:

```bash
make data SEED=42 SCENARIO=baseline
```

The same seed plus scenario rewrites byte-identical files. `metadata.json` records the scenario config, requested seed, effective seed, generator version, and output file list. Every CSV also includes `scenario` and `seed` columns.

## Scenarios

- `baseline.yaml`: normal operating conditions, moderate demand, no disruptions.
- `component-shortage-shock.yaml`: inbound raw-component shortage; selected supplier-to-plant lanes go to zero capacity for configured periods and lead times spike.
- `demand-surge.yaml`: finished-goods demand multiplier over configured periods.
- `stress-large.yaml`: larger network, higher variance, demand surge plus inbound disruption pressure.

## Units

- Period: one planning period, currently weekly in all configs.
- Demand, capacity, and inventory quantities: units per period unless a column says otherwise.
- Lead time: days.
- Cost: arbitrary currency units per unit, order, or kilometer as named by the column.
- Distance: kilometers.

## Output Schema

### `metadata.json`

JSON object with:

- `generator`: string identifier.
- `generator_version`: integer schema/generator version.
- `scenario`: scenario name.
- `requested_seed`: CLI seed.
- `seed`: effective seed used by the RNG.
- `random_seed_override`: null or scenario-provided override.
- `scenario_config`: full parsed scenario config.
- `outputs`: generated file list.
- `synthetic_data_notice`: explicit no-customer-data notice.

### `nodes.csv`

Network topology nodes.

| Column | Type | Unit / Meaning |
|---|---:|---|
| `node_id` | string | Stable ID: `SUP-*`, `PLANT-*`, `DC-*`, `CUST-*` |
| `node_type` | string | `supplier`, `plant`, `distribution_center`, `customer` |
| `name` | string | Synthetic display name |
| `region` | string | Synthetic region bucket |
| `capacity_units_per_period` | int | Throughput cap for supplier/plant/DC nodes |
| `storage_capacity_units` | int | Storage cap |
| `scenario` | string | Scenario name |
| `seed` | int | Effective seed |

Relationships: `node_id` is referenced by lanes, demand, and inventory.

### `skus.csv`

Item master and SKU-level cost parameters.

| Column | Type | Unit / Meaning |
|---|---:|---|
| `sku_id` | string | `FG-*`, `SA-*`, `RC-*` |
| `sku_type` | string | `finished_good`, `subassembly`, `raw_component` |
| `description` | string | Synthetic item name |
| `unit_holding_cost` | float | Cost per unit per period |
| `ordering_cost` | float | Fixed order/setup cost |
| `backorder_penalty` | float | Penalty per delayed unit |
| `lost_sale_penalty` | float | Penalty per lost unit |
| `production_cost` | float | Production/conversion cost per unit |
| `unit_volume_cubic_m` | float | Volume per unit |
| `scenario` | string | Scenario name |
| `seed` | int | Effective seed |

### `bom.csv`

Multi-tier bill of materials.

| Column | Type | Unit / Meaning |
|---|---:|---|
| `parent_sku_id` | string | Parent SKU |
| `component_sku_id` | string | Required component SKU |
| `quantity_per_parent` | int | Component units required per parent unit |
| `tier_depth` | int | `1` for finished good to subassembly, `2` for subassembly to raw component |
| `scenario` | string | Scenario name |
| `seed` | int | Effective seed |

Relationships: every finished good has at least one tier-1 subassembly and each subassembly has tier-2 raw components.

### `demand.csv`

Finished-goods customer demand plus BOM-derived component demand.

| Column | Type | Unit / Meaning |
|---|---:|---|
| `period` | int | Planning period |
| `demand_type` | string | `finished_good_customer` or `derived_component` |
| `node_id` | string | Customer node for finished goods; plant node for derived component load |
| `sku_id` | string | Demanded SKU |
| `parent_finished_good_id` | string | Finished good driving the row |
| `quantity_units` | int | Demand quantity |
| `base_quantity_units` | float | Pre-factor base quantity, or derived component quantity |
| `seasonal_factor` | float | Seasonal multiplier |
| `trend_factor` | float | Trend multiplier |
| `noise_multiplier` | float | Lognormal noise multiplier |
| `lump_multiplier` | float | Intermittent/lumpy multiplier |
| `shock_multiplier` | float | Demand-shock multiplier |
| `scenario` | string | Scenario name |
| `seed` | int | Effective seed |

Relationships: component rows are recursively derived from finished-goods rows through `bom.csv`, so component demand is correlated with finished-goods demand by construction.

### `production_lines.csv`

Line-level manufacturing capacity.

| Column | Type | Unit / Meaning |
|---|---:|---|
| `line_id` | string | Stable production line ID |
| `plant_id` | string | Plant node owning the line |
| `sku_id` | string | Primary finished good assigned to the line |
| `max_throughput_units_per_period` | int | Line capacity |
| `scenario` | string | Scenario name |
| `seed` | int | Effective seed |

Relationships: `plant_id` references `nodes.node_id`; plant node capacity is the total ceiling above line capacities.

### `lanes.csv`

Multi-echelon logistics lanes.

| Column | Type | Unit / Meaning |
|---|---:|---|
| `lane_id` | string | Stable lane ID |
| `from_node_id` | string | Origin node |
| `to_node_id` | string | Destination node |
| `lane_type` | string | `inbound_raw`, `plant_to_dc`, `dc_to_customer` |
| `sku_scope` | string | Raw component ID or `finished_goods` |
| `lead_time_mean_days` | float | Lead-time mean |
| `lead_time_std_days` | float | Lead-time standard deviation |
| `lane_cost_per_unit` | float | Lane handling/transport cost per unit |
| `capacity_units_per_period` | int | Nominal lane capacity |
| `distance_km` | int | Lane distance |
| `transport_cost_per_km` | float | Distance cost parameter |
| `co2_kg_per_unit` | float | Emissions proxy |
| `lane_ordinal` | int | Deterministic ordering helper |
| `scenario` | string | Scenario name |
| `seed` | int | Effective seed |

Relationships: `from_node_id` and `to_node_id` reference `nodes.node_id`.

### `lane_periods.csv`

Period-specific lane capacity and lead time after disruptions.

| Column | Type | Unit / Meaning |
|---|---:|---|
| `lane_id` | string | References `lanes.lane_id` |
| `period` | int | Planning period |
| `effective_capacity_units` | int | Capacity after disruption multiplier |
| `effective_lead_time_mean_days` | float | Lead time after disruption multiplier |
| `capacity_multiplier` | float | Applied capacity multiplier |
| `lead_time_multiplier` | float | Applied lead-time multiplier |
| `disruption_code` | string | Empty or scenario disruption name |
| `scenario` | string | Scenario name |
| `seed` | int | Effective seed |

### `service_targets.csv`

Customer/SKU service targets.

| Column | Type | Unit / Meaning |
|---|---:|---|
| `customer_id` | string | Customer node |
| `sku_id` | string | Finished good |
| `fill_rate_target` | float | Target fill rate in `[0, 1]` |
| `days_inventory_target` | float | Target days of inventory |
| `criticality_tier` | string | Synthetic priority label |
| `scenario` | string | Scenario name |
| `seed` | int | Effective seed |

### `initial_inventory.csv`

Synthetic starting inventory state for future ingest/baseline phases.

| Column | Type | Unit / Meaning |
|---|---:|---|
| `node_id` | string | Customer node |
| `sku_id` | string | Finished good |
| `on_hand_units` | int | Starting on-hand inventory |
| `in_transit_units` | int | Starting in-transit inventory |
| `backlog_units` | int | Starting backlog |
| `scenario` | string | Scenario name |
| `seed` | int | Effective seed |
