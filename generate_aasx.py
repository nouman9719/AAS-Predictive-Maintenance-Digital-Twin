import argparse
import csv
import re
from collections.abc import Iterator
from pathlib import Path

from basyx.aas import model
from basyx.aas.adapter.aasx import AASXWriter, DictSupplementaryFileContainer


DATASET_URL = (
    "https://archive.ics.uci.edu/dataset/601/"
    "ai4i+2020+predictive+maintenance+dataset"
)
DEFAULT_INPUT = Path(__file__).with_name("ai4i_sample.csv")
BASE = "https://example.org/ai4i"
FAILURE_COLUMNS = ("Machine failure", "TWF", "HDF", "PWF", "OSF", "RNF")


def iter_records(path: Path) -> Iterator[dict[str, str]]:
    """Stream rows one at a time, normalizing the dataset's wrapped headers."""
    with path.open(newline="", encoding="utf-8-sig") as csv_file:
        for raw_record in csv.DictReader(csv_file):
            yield {
                re.sub(r"\s+", " ", key).strip(): value.strip()
                for key, value in raw_record.items()
                if key is not None and value is not None
            }


def make_property(name: str | None, value_type: type, value: object) -> model.Property:
    return model.Property(id_short=name, value_type=value_type, value=value)


def make_submodel(
    owner: str, name: str, elements: list[model.SubmodelElement]
) -> model.Submodel:
    # Submodel ids must be globally unique, so they are scoped to the owning asset.
    return model.Submodel(
        id_=f"{BASE}/submodels/{owner}/{name}",
        id_short=name,
        submodel_element=elements,
    )


def operating_conditions(record: dict[str, str]) -> list[model.Property]:
    """Fresh measurement properties (an element can only have one parent)."""
    return [
        make_property("AirTemperatureK", float, float(record["Air temperature [K]"])),
        make_property(
            "ProcessTemperatureK", float, float(record["Process temperature [K]"])
        ),
        make_property("RotationalSpeedRpm", int, int(record["Rotational speed [rpm]"])),
        make_property("TorqueNm", float, float(record["Torque [Nm]"])),
        make_property("ToolWearMin", int, int(record["Tool wear [min]"])),
    ]


def failure_flags(record: dict[str, str]) -> list[model.Property]:
    return [
        make_property(
            "MachineFailure" if column == "Machine failure" else column,
            bool,
            record[column] == "1",
        )
        for column in FAILURE_COLUMNS
    ]


def make_shell(
    shell_key: str, submodels: list[model.Submodel], asset_type: str
) -> model.AssetAdministrationShell:
    return model.AssetAdministrationShell(
        id_=f"{BASE}/assets/{shell_key}",
        id_short=f"AI4I{shell_key}",
        asset_information=model.AssetInformation(
            asset_kind=model.AssetKind.INSTANCE,
            global_asset_id=f"urn:example:ai4i:asset:{shell_key}",
            asset_type=asset_type,
        ),
        submodel={
            model.ModelReference(
                key=(model.Key(model.KeyTypes.SUBMODEL, sm.id),),
                type_=model.Submodel,
            )
            for sm in submodels
        },
    )


def build_row_shell(record: dict[str, str]) -> list[model.Identifiable]:
    """One shell (plus its submodels) for a single dataset row."""
    key = record["Product ID"]
    submodels = [
        make_submodel(
            key,
            "AssetIdentification",
            [
                make_property("ProductId", str, key),
                make_property("ProductType", str, record["Type"]),
            ],
        ),
        make_submodel(key, "OperatingConditions", operating_conditions(record)),
        make_submodel(key, "FailureStatus", failure_flags(record)),
        make_submodel(
            key,
            "DatasetProvenance",
            [
                make_property("DatasetName", str, "AI4I 2020 Predictive Maintenance"),
                make_property("DatasetRowId", str, record["UDI"]),
                make_property("Source", str, DATASET_URL),
            ],
        ),
    ]
    shell = make_shell(key, submodels, "AI4I product with machine-condition record")
    return [shell, *submodels]


def build_timeseries_shell(
    records: list[dict[str, str]], machine_id: str
) -> list[model.Identifiable]:
    """One shell for one machine whose history is a list of sample collections."""
    samples = []
    for record in records:
        # Items of a SubmodelElementList carry no idShort.
        samples.append(
            model.SubmodelElementCollection(
                id_short=None,
                value=[
                    make_property("SampleId", str, record["UDI"]),
                    *operating_conditions(record),
                    model.SubmodelElementCollection(
                        id_short="Failures", value=failure_flags(record)
                    ),
                ],
            )
        )

    history = model.SubmodelElementList(
        id_short="Samples",
        type_value_list_element=model.SubmodelElementCollection,
        value=samples,
        order_relevant=True,  # list position is the time order
    )
    submodels = [
        make_submodel(
            machine_id,
            "AssetIdentification",
            [make_property("MachineId", str, machine_id)],
        ),
        make_submodel(
            machine_id,
            "TimeSeries",
            [
                make_property("SampleCount", int, len(samples)),
                make_property("Source", str, DATASET_URL),
                history,
            ],
        ),
    ]
    shell = make_shell(machine_id, submodels, "Machine with sampled condition history")
    return [shell, *submodels]


def write_package(objects: list[model.Identifiable], output: Path) -> None:
    store = model.DictIdentifiableStore(objects)
    shells = [o for o in objects if isinstance(o, model.AssetAdministrationShell)]
    files = DictSupplementaryFileContainer()
    output.parent.mkdir(parents=True, exist_ok=True)
    with AASXWriter(output, failsafe=False) as writer:
        # One call for all shells: each call writes the same data part.
        writer.write_aas([s.id for s in shells], store, files, write_json=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create AASX packages from AI4I dataset rows."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--mode",
        choices=("rows", "timeseries"),
        default="rows",
        help="rows: one shell per row; timeseries: one shell with all rows as samples.",
    )
    parser.add_argument("--udi", help="Only process this row identifier (UDI).")
    parser.add_argument("--limit", type=int, help="Process at most N rows.")
    parser.add_argument("--output", type=Path, help="Output .aasx (single package).")
    parser.add_argument(
        "--split-dir",
        type=Path,
        help="rows mode: write one .aasx per row into this directory instead.",
    )
    args = parser.parse_args()

    selected = []
    for record in iter_records(args.input):
        if args.limit is not None and len(selected) >= args.limit:
            break
        if args.udi is None or record["UDI"] == args.udi:
            selected.append(record)
    if not selected:
        raise SystemExit(f"No matching rows in {args.input}")

    if args.mode == "timeseries":
        machine_id = "Machine1"
        output = args.output or Path(f"AI4I{machine_id}.aasx")
        write_package(build_timeseries_shell(selected, machine_id), output)
        print(f"Created {output}: 1 shell, {len(selected)} samples.")
    elif args.split_dir:
        for record in selected:
            write_package(
                build_row_shell(record),
                args.split_dir / f"AI4I{record['Product ID']}.aasx",
            )
        print(f"Created {len(selected)} packages in {args.split_dir}.")
    else:
        objects = [o for record in selected for o in build_row_shell(record)]
        output = args.output or (
            Path(f"AI4I{selected[0]['Product ID']}.aasx")
            if len(selected) == 1
            else Path("AI4I_fleet.aasx")
        )
        write_package(objects, output)
        print(f"Created {output}: {len(selected)} shells.")


if __name__ == "__main__":
    main()
