"""Label availability is distinct from admission as an independent target."""


def label_admission(columns: dict[str, str], metadata: dict) -> dict:
    return {**metadata, "status": "PENDING", "silent_target_replacement": False,
            "current_skeleton_target": "NH4_N", "intended_target": "TN",
            "targets": [{"target": name, "source_column": column, "column_present": True,
                         "sampling_location": "UNKNOWN", "native_support": "UNKNOWN",
                         "averaging_and_latency": "UNKNOWN", "lab_comparison": "PENDING",
                         "observation_operator": "PENDING", "available_at": None,
                         "independent_label_admitted": False,
                         "reason": "aligned_column_presence_does_not_establish_independent_native_label"}
                        for name, column in columns.items()]}
