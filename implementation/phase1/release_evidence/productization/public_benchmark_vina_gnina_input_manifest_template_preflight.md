# Public Benchmark Vina/GNINA Input Manifest Template Preflight

- `status`: `operator_manifest_complete`
- `contract_pass`: `True`
- `manifest_ready`: `True`
- `template_row_count`: `12`
- `missing_required_value_count`: `0`
- `unsupported_benchmark_field_count`: `0`
- `invalid_source_receipt_count`: `0`
- `missing_local_file_count`: `0`
- `missing_receipt_ref_count`: `0`
- `source_file_missing_count`: `0`
- `source_url_probe_count`: `1`
- `known_source_url_content_length_gib`: `1.465`
- `prepared_input_missing_count`: `0`
- `receipt_ref_missing_count`: `0`

## Case Rows

| Case | Status | Missing Fields | Missing Files | Missing Refs |
|---|---|---|---|---|
| `casf2016_4llx` | `ready` | `0` | `0` | `0` |
| `casf2016_5c28` | `ready` | `0` | `0` | `0` |
| `casf2016_3uuo` | `ready` | `0` | `0` | `0` |
| `casf2016_3ui7` | `ready` | `0` | `0` | `0` |
| `casf2016_5c2h` | `ready` | `0` | `0` | `0` |
| `casf2016_2v00` | `ready` | `0` | `0` | `0` |
| `casf2016_3wz8` | `ready` | `0` | `0` | `0` |
| `casf2016_3pww` | `ready` | `0` | `0` | `0` |
| `casf2016_3prs` | `ready` | `0` | `0` | `0` |
| `casf2016_3uri` | `ready` | `0` | `0` | `0` |
| `casf2016_4m0z` | `ready` | `0` | `0` | `0` |
| `casf2016_4m0y` | `ready` | `0` | `0` | `0` |

## Source File Acquisition Plan

| Case | Role | Path | Expected Checksum | Status | Action |
|---|---|---|---|---|---|
| `casf2016_4llx` | `source_protein_structure` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/4llx/4llx_protein.pdb` | `sha256:ee6be565638c58d9b608a5cb79a98dae39566a60b4ae019ea6a23a45c2b7a834` | `ready` | `verify_local_source_file_checksum` |
| `casf2016_4llx` | `source_reference_ligand` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/4llx/4llx_ligand.sdf` | `sha256:a6298d4cdddb5d1926ca09bcb5e1412ecd2699476f3ae1fa086d3d335efaa6f1` | `ready` | `verify_local_source_file_checksum` |
| `casf2016_5c28` | `source_protein_structure` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/5c28/5c28_protein.pdb` | `sha256:ac3677c62abb2e549c4e3f4a6185663da16028e7e1b1e6ef875da956e77639b0` | `ready` | `verify_local_source_file_checksum` |
| `casf2016_5c28` | `source_reference_ligand` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/5c28/5c28_ligand.sdf` | `sha256:7df337dcb033a69f6db8d229749489e45ba9695a4a2e9bdf5593a51ae66eaf87` | `ready` | `verify_local_source_file_checksum` |
| `casf2016_3uuo` | `source_protein_structure` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/3uuo/3uuo_protein.pdb` | `sha256:80b28a058a5a2da46bc2e3e91e26c1e14c4f2fd7514c051559b017ab0e93dcf9` | `ready` | `verify_local_source_file_checksum` |
| `casf2016_3uuo` | `source_reference_ligand` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/3uuo/3uuo_ligand.sdf` | `sha256:7eedba7f908c0ba267dbe8af02294fcd148064d25cde772d62dded9737258ce5` | `ready` | `verify_local_source_file_checksum` |
| `casf2016_3ui7` | `source_protein_structure` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/3ui7/3ui7_protein.pdb` | `sha256:62a51c4d5a96b8b2b0388e1e9f9dc55763d39996935f1ed30c1bdfd2ef282e0e` | `ready` | `verify_local_source_file_checksum` |
| `casf2016_3ui7` | `source_reference_ligand` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/3ui7/3ui7_ligand.sdf` | `sha256:bc6913724d6339af7844e5dedb93010e6e7e706c8da629d1e54a73c2fd2eafa2` | `ready` | `verify_local_source_file_checksum` |
| `casf2016_5c2h` | `source_protein_structure` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/5c2h/5c2h_protein.pdb` | `sha256:59718184b6c4de964136707cca00f1eb1361fff3d24020e28878dbec60e67917` | `ready` | `verify_local_source_file_checksum` |
| `casf2016_5c2h` | `source_reference_ligand` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/5c2h/5c2h_ligand.sdf` | `sha256:7c512908ac4e7157027219b8f09bcede70f8d0621606303a5ff2eceb89033420` | `ready` | `verify_local_source_file_checksum` |
| `casf2016_2v00` | `source_protein_structure` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/2v00/2v00_protein.pdb` | `sha256:ce00145b46da36a51792628b6322437c7acb30cbc6c165c47443a1ed3d2256fa` | `ready` | `verify_local_source_file_checksum` |
| `casf2016_2v00` | `source_reference_ligand` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/2v00/2v00_ligand.sdf` | `sha256:cc87334e0ed4d4d66929e57998fae43785bbe399772967f8a660dfbc106c9b16` | `ready` | `verify_local_source_file_checksum` |
| `casf2016_3wz8` | `source_protein_structure` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/3wz8/3wz8_protein.pdb` | `sha256:9de2f60abeea752abc06f866597255ca08fe75bf09cc749f76951adc30b0b45f` | `ready` | `verify_local_source_file_checksum` |
| `casf2016_3wz8` | `source_reference_ligand` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/3wz8/3wz8_ligand.sdf` | `sha256:33a3b8306ae40623d38a5af2a883037a17472f18ba58141456f7bdf8abedb03a` | `ready` | `verify_local_source_file_checksum` |
| `casf2016_3pww` | `source_protein_structure` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/3pww/3pww_protein.pdb` | `sha256:351db504aee7d52f588e720c0f9d88ceb65fa738aa9a3d393ec5cbed4af96efb` | `ready` | `verify_local_source_file_checksum` |
| `casf2016_3pww` | `source_reference_ligand` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/3pww/3pww_ligand.sdf` | `sha256:e4cc5a4f6f900a00cd2ce5976a3603d38204f0c288774f5650e35ab7e6324d0b` | `ready` | `verify_local_source_file_checksum` |
| `casf2016_3prs` | `source_protein_structure` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/3prs/3prs_protein.pdb` | `sha256:6a294ddeb8eaaf9a876ac9ad7a3e2715da586fdb7877d4cac306d4348932e34b` | `ready` | `verify_local_source_file_checksum` |
| `casf2016_3prs` | `source_reference_ligand` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/3prs/3prs_ligand.sdf` | `sha256:4625a72478cc0940022b39b2059e0d7115a20eaf6b845ecde8b17a195fba0911` | `ready` | `verify_local_source_file_checksum` |
| `casf2016_3uri` | `source_protein_structure` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/3uri/3uri_protein.pdb` | `sha256:03b1b8c59bd72520faca258f2a1c4a5677e161bf3ace4a9df3ae7003d585f8b1` | `ready` | `verify_local_source_file_checksum` |
| `casf2016_3uri` | `source_reference_ligand` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/3uri/3uri_ligand.sdf` | `sha256:9091e3949535eeae0afa1e80484ece0e71e6809c44d81072130b54f81f440a85` | `ready` | `verify_local_source_file_checksum` |
| `casf2016_4m0z` | `source_protein_structure` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/4m0z/4m0z_protein.pdb` | `sha256:8eb56910faa3eb78ca1b8c244b01bf6094f2838a4db08a0b5198b68e6a96242d` | `ready` | `verify_local_source_file_checksum` |
| `casf2016_4m0z` | `source_reference_ligand` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/4m0z/4m0z_ligand.sdf` | `sha256:533af481c8fe734256312a30791bfbb12eb5796e26409942c66581fb8ef60f07` | `ready` | `verify_local_source_file_checksum` |
| `casf2016_4m0y` | `source_protein_structure` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/4m0y/4m0y_protein.pdb` | `sha256:f2b1040546ed7c6d01e4ef39996afcc283be189a42df7bde3773db0d2ecbe7bc` | `ready` | `verify_local_source_file_checksum` |
| `casf2016_4m0y` | `source_reference_ligand` | `tmp/public_benchmark_vina_gnina/casf2016_source_files/CASF-2016/coreset/4m0y/4m0y_ligand.sdf` | `sha256:65f2c98b8958e739f98b243924513e3ff3068d536665a7b0e27fefa81a0e0dfc` | `ready` | `verify_local_source_file_checksum` |

## Source URL Probe Plan

| URL | Status | Size Bytes | Cases |
|---|---|---:|---:|
| `https://static.pdbbind-plus.org.cn/download/CASF-2016.tar.gz` | `reachable` | `1572660769` | `12` |

## Prepared Input Plan

| Case | Role | Path | Expected Checksum | Status | Action |
|---|---|---|---|---|---|
| `casf2016_4llx` | `prepared_receptor` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_4llx/4llx_receptor.pdbqt` | `sha256:de03ccd0af958764fa4b939728ee729e98999c897176ab901f3476c931fb4ab8` | `ready` | `verify_prepared_input_file_checksum` |
| `casf2016_4llx` | `prepared_ligand` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_4llx/4llx_ligand.pdbqt` | `sha256:1ea1c5148e59b2a4d189095e75440dc172f6b6e46d6fe35004048f01e8e65ccd` | `ready` | `verify_prepared_input_file_checksum` |
| `casf2016_5c28` | `prepared_receptor` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_5c28/5c28_receptor.pdbqt` | `sha256:c4e44d5e67a00d2223405f8803b1fe18d162b15b57a598929493c3e85ffa7f4c` | `ready` | `verify_prepared_input_file_checksum` |
| `casf2016_5c28` | `prepared_ligand` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_5c28/5c28_ligand.pdbqt` | `sha256:be86ee1b5eed370876ca35b328c2ec487ee7f167e14078d4c831729597faac25` | `ready` | `verify_prepared_input_file_checksum` |
| `casf2016_3uuo` | `prepared_receptor` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3uuo/3uuo_receptor.pdbqt` | `sha256:252f38e441c93b3e6f90c625366d09d56720f6029b11c91c615a91e97c432c90` | `ready` | `verify_prepared_input_file_checksum` |
| `casf2016_3uuo` | `prepared_ligand` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3uuo/3uuo_ligand.pdbqt` | `sha256:633ff433b4efae605d0fa8e76dd6edeeb5c178c4af2c376b863cedbef3d6e99c` | `ready` | `verify_prepared_input_file_checksum` |
| `casf2016_3ui7` | `prepared_receptor` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3ui7/3ui7_receptor.pdbqt` | `sha256:1a2174ecb65e1aa8a14dce024df7b0993275ce071c2eda0e7f8eb4a8d00dbb05` | `ready` | `verify_prepared_input_file_checksum` |
| `casf2016_3ui7` | `prepared_ligand` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3ui7/3ui7_ligand.pdbqt` | `sha256:992502112eee802f34ccf4089c19dfdbf52647a3c97a510c37d4493ec5f831ba` | `ready` | `verify_prepared_input_file_checksum` |
| `casf2016_5c2h` | `prepared_receptor` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_5c2h/5c2h_receptor.pdbqt` | `sha256:294fb92f1a79fa28b7871b18e61b75921efd1891ab7ed2dc1cf5d7a40bac8525` | `ready` | `verify_prepared_input_file_checksum` |
| `casf2016_5c2h` | `prepared_ligand` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_5c2h/5c2h_ligand.pdbqt` | `sha256:6c5ff1eb25d254d7026c21533cb0a91d155d911feab3d39ce76b028cd15a876d` | `ready` | `verify_prepared_input_file_checksum` |
| `casf2016_2v00` | `prepared_receptor` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_2v00/2v00_receptor.pdbqt` | `sha256:7b5b15472e5934b3fa08e386a47a7747a2689da7a2e729246e5f5ce8e6c91e82` | `ready` | `verify_prepared_input_file_checksum` |
| `casf2016_2v00` | `prepared_ligand` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_2v00/2v00_ligand.pdbqt` | `sha256:0f6325b1cfdabdb78d4c2791078731664a12482541c661a07c05b1abbc652c54` | `ready` | `verify_prepared_input_file_checksum` |
| `casf2016_3wz8` | `prepared_receptor` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3wz8/3wz8_receptor.pdbqt` | `sha256:83a5be536e85345f0776aaafe140e4dc64c9f583e0b6eaf906e5f3296a17e8a4` | `ready` | `verify_prepared_input_file_checksum` |
| `casf2016_3wz8` | `prepared_ligand` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3wz8/3wz8_ligand.pdbqt` | `sha256:7911ee3d3af3154a9071b2de31779d84daaac26270ddb7160eeb7a231fb77b4d` | `ready` | `verify_prepared_input_file_checksum` |
| `casf2016_3pww` | `prepared_receptor` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3pww/3pww_receptor.pdbqt` | `sha256:17059aae4c030f34f327ccb8a5437b05455752ae60c6bf4ac9d840478350430c` | `ready` | `verify_prepared_input_file_checksum` |
| `casf2016_3pww` | `prepared_ligand` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3pww/3pww_ligand.pdbqt` | `sha256:71934fbaef24028a7d2eb7ebd71d1358ad49473b35b16efc82dd41f2dac7c4b3` | `ready` | `verify_prepared_input_file_checksum` |
| `casf2016_3prs` | `prepared_receptor` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3prs/3prs_receptor.pdbqt` | `sha256:8b236ea8493e3d3bc34d7cdf8fc8b5a361c38a7f13b90f6e1f5999755b219c6b` | `ready` | `verify_prepared_input_file_checksum` |
| `casf2016_3prs` | `prepared_ligand` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3prs/3prs_ligand.pdbqt` | `sha256:42a99318198c06fb4e3d78f8e56402c5e04a85482a68d5d3da913547da231b51` | `ready` | `verify_prepared_input_file_checksum` |
| `casf2016_3uri` | `prepared_receptor` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3uri/3uri_receptor.pdbqt` | `sha256:87910269466b6668c1ca9449910cd48841b9c656c6fcd6fb40da941a173c7fb6` | `ready` | `verify_prepared_input_file_checksum` |
| `casf2016_3uri` | `prepared_ligand` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3uri/3uri_ligand.pdbqt` | `sha256:8aaa32fe9843effcaf655153fd7f6539bb854f339219e75c91586b81cc3de62c` | `ready` | `verify_prepared_input_file_checksum` |
| `casf2016_4m0z` | `prepared_receptor` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_4m0z/4m0z_receptor.pdbqt` | `sha256:e0a7daa8114a4ba431e6cde226b924d4d2f291795f5f9487680b60f691d61caa` | `ready` | `verify_prepared_input_file_checksum` |
| `casf2016_4m0z` | `prepared_ligand` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_4m0z/4m0z_ligand.pdbqt` | `sha256:6b5e58de803b33b3db9ac673c039c16ecb50d05dd44c9b7267acdf495a11bde8` | `ready` | `verify_prepared_input_file_checksum` |
| `casf2016_4m0y` | `prepared_receptor` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_4m0y/4m0y_receptor.pdbqt` | `sha256:33a93c55125ea350e629c33081850a2572b6efe98aeae71ffcdda40b92af1967` | `ready` | `verify_prepared_input_file_checksum` |
| `casf2016_4m0y` | `prepared_ligand` | `tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_4m0y/4m0y_ligand.pdbqt` | `sha256:85d125f04c88337c6546ff759b6431483a75d5a29ca338ce76eed7c41bf0d783` | `ready` | `verify_prepared_input_file_checksum` |

## Receipt Ref Plan

| Case | Field | Ref | Status | Action |
|---|---|---|---|---|
| `casf2016_4llx` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_4llx/vina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_4llx` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_4llx/gnina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_4llx` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_4llx/vina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_4llx` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_4llx/gnina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_4llx` | `input_preparation_provenance_ref` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_prepared_inputs_report.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_5c28` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_5c28/vina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_5c28` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_5c28/gnina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_5c28` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_5c28/vina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_5c28` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_5c28/gnina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_5c28` | `input_preparation_provenance_ref` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_prepared_inputs_report.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3uuo` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_3uuo/vina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3uuo` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_3uuo/gnina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3uuo` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3uuo/vina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3uuo` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3uuo/gnina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3uuo` | `input_preparation_provenance_ref` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_prepared_inputs_report.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3ui7` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_3ui7/vina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3ui7` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_3ui7/gnina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3ui7` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3ui7/vina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3ui7` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3ui7/gnina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3ui7` | `input_preparation_provenance_ref` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_prepared_inputs_report.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_5c2h` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_5c2h/vina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_5c2h` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_5c2h/gnina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_5c2h` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_5c2h/vina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_5c2h` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_5c2h/gnina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_5c2h` | `input_preparation_provenance_ref` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_prepared_inputs_report.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_2v00` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_2v00/vina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_2v00` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_2v00/gnina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_2v00` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_2v00/vina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_2v00` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_2v00/gnina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_2v00` | `input_preparation_provenance_ref` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_prepared_inputs_report.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3wz8` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_3wz8/vina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3wz8` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_3wz8/gnina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3wz8` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3wz8/vina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3wz8` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3wz8/gnina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3wz8` | `input_preparation_provenance_ref` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_prepared_inputs_report.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3pww` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_3pww/vina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3pww` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_3pww/gnina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3pww` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3pww/vina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3pww` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3pww/gnina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3pww` | `input_preparation_provenance_ref` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_prepared_inputs_report.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3prs` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_3prs/vina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3prs` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_3prs/gnina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3prs` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3prs/vina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3prs` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3prs/gnina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3prs` | `input_preparation_provenance_ref` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_prepared_inputs_report.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3uri` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_3uri/vina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3uri` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_3uri/gnina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3uri` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3uri/vina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3uri` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3uri/gnina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_3uri` | `input_preparation_provenance_ref` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_prepared_inputs_report.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_4m0z` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_4m0z/vina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_4m0z` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_4m0z/gnina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_4m0z` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_4m0z/vina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_4m0z` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_4m0z/gnina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_4m0z` | `input_preparation_provenance_ref` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_prepared_inputs_report.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_4m0y` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_4m0y/vina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_4m0y` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_4m0y/gnina_config.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_4m0y` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_4m0y/vina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_4m0y` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_4m0y/gnina_run_receipt.json` | `ready` | `verify_manifest_receipt_ref` |
| `casf2016_4m0y` | `input_preparation_provenance_ref` | `implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_prepared_inputs_report.json` | `ready` | `verify_manifest_receipt_ref` |

## Commands

- `write_preflight`: `python3 scripts/build_public_benchmark_vina_gnina_input_manifest_template_preflight.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.json --out-md implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.md`
- `probe_source_urls`: `python3 scripts/build_public_benchmark_vina_gnina_input_manifest_template_preflight.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.json --out-md implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.md --probe-source-urls`
- `materialize_input_manifest_from_casf_archive`: `python3 scripts/materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive.py --archive <CASF-2016.tar.gz> --extract-dir tmp/public_benchmark_vina_gnina/casf2016_source_files --out-manifest implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest.csv --out-report implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_from_casf_archive_report.json`
- `materialize_input_manifest_working_copy_from_template`: `python3 scripts/materialize_public_benchmark_vina_gnina_input_manifest_from_template.py --template implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template.csv --out-manifest implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest.csv --out-report implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_from_template_report.json`
- `rerun_execution_plan`: `python3 scripts/build_public_benchmark_vina_gnina_execution_plan.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_execution_plan.json`
- `rerun_runtime_readiness`: `python3 scripts/build_public_benchmark_vina_gnina_runtime_readiness.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_runtime_readiness.json`

This preflight audits the operator input-manifest template only. It does not promote the template to an actual manifest, verify license rights, run Vina/GNINA, create adapter rows, or close Public Benchmark Phase 2.
