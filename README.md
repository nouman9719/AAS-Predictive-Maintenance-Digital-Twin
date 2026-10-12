# AI4I AAS Starter

A small, inspectable example that maps one row of the UCI AI4I predictive-maintenance dataset into an Asset Administration Shell (AAS) package.

## Model

```text
AssetAdministrationShell: AI4IM14860
  AssetIdentification
    ProductId, ProductType
  OperatingConditions
    AirTemperature, ProcessTemperature, RotationalSpeed, Torque, ToolWear
  FailureStatus
    MachineFailure, TWF, HDF, PWF, OSF, RNF
  DatasetProvenance
    DatasetName, DatasetRowId, Source
```

The shell identifies the sample product record. Each submodel groups information for a purpose, and each property is one typed data element. This example is a static snapshot from one dataset row, not an identified physical machine or a live connection to a sensor.

| Source column | AAS location | Type / unit |
| --- | --- | --- |
| `Product ID` | `AssetIdentification.ProductId` | string |
| `Type` | `AssetIdentification.ProductType` | string |
| `Air temperature [K]` | `OperatingConditions.AirTemperature` | float, K |
| `Process temperature [K]` | `OperatingConditions.ProcessTemperature` | float, K |
| `Rotational speed [rpm]` | `OperatingConditions.RotationalSpeed` | integer, rpm |
| `Torque [Nm]` | `OperatingConditions.Torque` | float, N*m |
| `Tool wear [min]` | `OperatingConditions.ToolWear` | integer, min |
| `Machine failure`, `TWF`, `HDF`, `PWF`, `OSF`, `RNF` | `FailureStatus` | boolean flags |
| `UDI` | `DatasetProvenance.DatasetRowId` | string |

The `idShort` names are for learning and readability; this first model does not assign standardized semantic identifiers to the properties.

## Generate the AASX

```sh
python -m pip install -r requirements.txt
python generate_aasx.py
```

This creates `AI4IM14860.aasx` in the current directory. Open that file in AASX Package Explorer and expand the shell, submodels, and properties to inspect the structure.

To use a row from the full dataset instead of the included one-row sample:

```sh
curl -L -o ai4i.zip 'https://archive.ics.uci.edu/static/public/601/ai4i+2020+predictive+maintenance+dataset.zip'
unzip -o ai4i.zip
python generate_aasx.py --input ai4i2020.csv --udi 1
```

Change `--udi` to another row's `UDI` value. The generator normalizes the dataset's line-wrapped `Rotational speed [rpm]` header.

## Scaling up: many shells and time series

The script streams the whole CSV and has two modes:

```sh
# One shell per row, all in one package (AI4I_fleet.aasx)
python generate_aasx.py --input ai4i2020.csv --limit 500

# Same, but one .aasx per row
python generate_aasx.py --input ai4i2020.csv --limit 500 --split-dir out/

# One shell whose TimeSeries submodel holds every row as a sample
python generate_aasx.py --input ai4i2020.csv --mode timeseries --limit 500
```

Time-series model: `TimeSeries.Samples` is an ordered `SubmodelElementList` whose items are `SubmodelElementCollection`s (`SampleId`, the five measurements, and a nested `Failures` collection). List items have no `idShort`; their position is the order. Submodel ids are scoped per asset (`.../submodels/<asset>/<name>`) so hundreds of shells never collide. Note AI4I rows are different products, so `timeseries` mode treats the rows as one machine's sequence purely as a modelling exercise. Very large histories bloat an AASX; real deployments keep the bulk data in a time-series store and reference it.

## Data source

The sample comes from the [UCI AI4I 2020 Predictive Maintenance Dataset](https://archive.ics.uci.edu/dataset/601/ai4i+2020+predictive+maintenance+dataset), by Matzka (2020), licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The included CSV contains only the first data row and retains its original values.