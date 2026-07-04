# Public Benchmark Vina/GNINA Input Manifest Template Preflight

- `status`: `operator_manifest_completion_required`
- `contract_pass`: `True`
- `manifest_ready`: `False`
- `template_row_count`: `12`
- `missing_required_value_count`: `36`
- `unsupported_benchmark_field_count`: `0`
- `invalid_source_receipt_count`: `0`
- `missing_local_file_count`: `48`
- `missing_receipt_ref_count`: `60`
- `source_file_missing_count`: `24`
- `source_url_probe_count`: `1`
- `known_source_url_content_length_gib`: `1.465`
- `prepared_input_missing_count`: `24`
- `receipt_ref_missing_count`: `60`

## Case Rows

| Case | Status | Missing Fields | Missing Files | Missing Refs |
|---|---|---|---|---|
| `casf2016_4llx` | `operator_completion_required` | `3` | `4` | `5` |
| `casf2016_5c28` | `operator_completion_required` | `3` | `4` | `5` |
| `casf2016_3uuo` | `operator_completion_required` | `3` | `4` | `5` |
| `casf2016_3ui7` | `operator_completion_required` | `3` | `4` | `5` |
| `casf2016_5c2h` | `operator_completion_required` | `3` | `4` | `5` |
| `casf2016_2v00` | `operator_completion_required` | `3` | `4` | `5` |
| `casf2016_3wz8` | `operator_completion_required` | `3` | `4` | `5` |
| `casf2016_3pww` | `operator_completion_required` | `3` | `4` | `5` |
| `casf2016_3prs` | `operator_completion_required` | `3` | `4` | `5` |
| `casf2016_3uri` | `operator_completion_required` | `3` | `4` | `5` |
| `casf2016_4m0z` | `operator_completion_required` | `3` | `4` | `5` |
| `casf2016_4m0y` | `operator_completion_required` | `3` | `4` | `5` |

## Source File Acquisition Plan

| Case | Role | Path | Expected Checksum | Status | Action |
|---|---|---|---|---|---|
| `casf2016_4llx` | `source_protein_structure` | `CASF-2016/coreset/4llx/4llx_protein.pdb` | `sha256:ee6be565638c58d9b608a5cb79a98dae39566a60b4ae019ea6a23a45c2b7a834` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |
| `casf2016_4llx` | `source_reference_ligand` | `CASF-2016/coreset/4llx/4llx_ligand.sdf` | `sha256:a6298d4cdddb5d1926ca09bcb5e1412ecd2699476f3ae1fa086d3d335efaa6f1` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |
| `casf2016_5c28` | `source_protein_structure` | `CASF-2016/coreset/5c28/5c28_protein.pdb` | `sha256:ac3677c62abb2e549c4e3f4a6185663da16028e7e1b1e6ef875da956e77639b0` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |
| `casf2016_5c28` | `source_reference_ligand` | `CASF-2016/coreset/5c28/5c28_ligand.sdf` | `sha256:7df337dcb033a69f6db8d229749489e45ba9695a4a2e9bdf5593a51ae66eaf87` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |
| `casf2016_3uuo` | `source_protein_structure` | `CASF-2016/coreset/3uuo/3uuo_protein.pdb` | `sha256:80b28a058a5a2da46bc2e3e91e26c1e14c4f2fd7514c051559b017ab0e93dcf9` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |
| `casf2016_3uuo` | `source_reference_ligand` | `CASF-2016/coreset/3uuo/3uuo_ligand.sdf` | `sha256:7eedba7f908c0ba267dbe8af02294fcd148064d25cde772d62dded9737258ce5` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |
| `casf2016_3ui7` | `source_protein_structure` | `CASF-2016/coreset/3ui7/3ui7_protein.pdb` | `sha256:62a51c4d5a96b8b2b0388e1e9f9dc55763d39996935f1ed30c1bdfd2ef282e0e` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |
| `casf2016_3ui7` | `source_reference_ligand` | `CASF-2016/coreset/3ui7/3ui7_ligand.sdf` | `sha256:bc6913724d6339af7844e5dedb93010e6e7e706c8da629d1e54a73c2fd2eafa2` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |
| `casf2016_5c2h` | `source_protein_structure` | `CASF-2016/coreset/5c2h/5c2h_protein.pdb` | `sha256:59718184b6c4de964136707cca00f1eb1361fff3d24020e28878dbec60e67917` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |
| `casf2016_5c2h` | `source_reference_ligand` | `CASF-2016/coreset/5c2h/5c2h_ligand.sdf` | `sha256:7c512908ac4e7157027219b8f09bcede70f8d0621606303a5ff2eceb89033420` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |
| `casf2016_2v00` | `source_protein_structure` | `CASF-2016/coreset/2v00/2v00_protein.pdb` | `sha256:ce00145b46da36a51792628b6322437c7acb30cbc6c165c47443a1ed3d2256fa` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |
| `casf2016_2v00` | `source_reference_ligand` | `CASF-2016/coreset/2v00/2v00_ligand.sdf` | `sha256:cc87334e0ed4d4d66929e57998fae43785bbe399772967f8a660dfbc106c9b16` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |
| `casf2016_3wz8` | `source_protein_structure` | `CASF-2016/coreset/3wz8/3wz8_protein.pdb` | `sha256:9de2f60abeea752abc06f866597255ca08fe75bf09cc749f76951adc30b0b45f` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |
| `casf2016_3wz8` | `source_reference_ligand` | `CASF-2016/coreset/3wz8/3wz8_ligand.sdf` | `sha256:33a3b8306ae40623d38a5af2a883037a17472f18ba58141456f7bdf8abedb03a` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |
| `casf2016_3pww` | `source_protein_structure` | `CASF-2016/coreset/3pww/3pww_protein.pdb` | `sha256:351db504aee7d52f588e720c0f9d88ceb65fa738aa9a3d393ec5cbed4af96efb` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |
| `casf2016_3pww` | `source_reference_ligand` | `CASF-2016/coreset/3pww/3pww_ligand.sdf` | `sha256:e4cc5a4f6f900a00cd2ce5976a3603d38204f0c288774f5650e35ab7e6324d0b` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |
| `casf2016_3prs` | `source_protein_structure` | `CASF-2016/coreset/3prs/3prs_protein.pdb` | `sha256:6a294ddeb8eaaf9a876ac9ad7a3e2715da586fdb7877d4cac306d4348932e34b` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |
| `casf2016_3prs` | `source_reference_ligand` | `CASF-2016/coreset/3prs/3prs_ligand.sdf` | `sha256:4625a72478cc0940022b39b2059e0d7115a20eaf6b845ecde8b17a195fba0911` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |
| `casf2016_3uri` | `source_protein_structure` | `CASF-2016/coreset/3uri/3uri_protein.pdb` | `sha256:03b1b8c59bd72520faca258f2a1c4a5677e161bf3ace4a9df3ae7003d585f8b1` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |
| `casf2016_3uri` | `source_reference_ligand` | `CASF-2016/coreset/3uri/3uri_ligand.sdf` | `sha256:9091e3949535eeae0afa1e80484ece0e71e6809c44d81072130b54f81f440a85` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |
| `casf2016_4m0z` | `source_protein_structure` | `CASF-2016/coreset/4m0z/4m0z_protein.pdb` | `sha256:8eb56910faa3eb78ca1b8c244b01bf6094f2838a4db08a0b5198b68e6a96242d` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |
| `casf2016_4m0z` | `source_reference_ligand` | `CASF-2016/coreset/4m0z/4m0z_ligand.sdf` | `sha256:533af481c8fe734256312a30791bfbb12eb5796e26409942c66581fb8ef60f07` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |
| `casf2016_4m0y` | `source_protein_structure` | `CASF-2016/coreset/4m0y/4m0y_protein.pdb` | `sha256:f2b1040546ed7c6d01e4ef39996afcc283be189a42df7bde3773db0d2ecbe7bc` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |
| `casf2016_4m0y` | `source_reference_ligand` | `CASF-2016/coreset/4m0y/4m0y_ligand.sdf` | `sha256:65f2c98b8958e739f98b243924513e3ff3068d536665a7b0e27fefa81a0e0dfc` | `operator_completion_required` | `materialize_source_files_from_casf_archive_and_verify_checksum` |

## Source URL Probe Plan

| URL | Status | Size Bytes | Cases |
|---|---|---:|---:|
| `https://static.pdbbind-plus.org.cn/download/CASF-2016.tar.gz` | `reachable` | `1572660769` | `12` |

## Prepared Input Plan

| Case | Role | Path | Expected Checksum | Status | Action |
|---|---|---|---|---|---|
| `casf2016_4llx` | `prepared_receptor` | `prepared/4llx_receptor` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |
| `casf2016_4llx` | `prepared_ligand` | `prepared/4llx_ligand` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |
| `casf2016_5c28` | `prepared_receptor` | `prepared/5c28_receptor` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |
| `casf2016_5c28` | `prepared_ligand` | `prepared/5c28_ligand` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |
| `casf2016_3uuo` | `prepared_receptor` | `prepared/3uuo_receptor` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |
| `casf2016_3uuo` | `prepared_ligand` | `prepared/3uuo_ligand` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |
| `casf2016_3ui7` | `prepared_receptor` | `prepared/3ui7_receptor` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |
| `casf2016_3ui7` | `prepared_ligand` | `prepared/3ui7_ligand` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |
| `casf2016_5c2h` | `prepared_receptor` | `prepared/5c2h_receptor` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |
| `casf2016_5c2h` | `prepared_ligand` | `prepared/5c2h_ligand` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |
| `casf2016_2v00` | `prepared_receptor` | `prepared/2v00_receptor` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |
| `casf2016_2v00` | `prepared_ligand` | `prepared/2v00_ligand` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |
| `casf2016_3wz8` | `prepared_receptor` | `prepared/3wz8_receptor` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |
| `casf2016_3wz8` | `prepared_ligand` | `prepared/3wz8_ligand` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |
| `casf2016_3pww` | `prepared_receptor` | `prepared/3pww_receptor` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |
| `casf2016_3pww` | `prepared_ligand` | `prepared/3pww_ligand` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |
| `casf2016_3prs` | `prepared_receptor` | `prepared/3prs_receptor` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |
| `casf2016_3prs` | `prepared_ligand` | `prepared/3prs_ligand` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |
| `casf2016_3uri` | `prepared_receptor` | `prepared/3uri_receptor` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |
| `casf2016_3uri` | `prepared_ligand` | `prepared/3uri_ligand` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |
| `casf2016_4m0z` | `prepared_receptor` | `prepared/4m0z_receptor` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |
| `casf2016_4m0z` | `prepared_ligand` | `prepared/4m0z_ligand` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |
| `casf2016_4m0y` | `prepared_receptor` | `prepared/4m0y_receptor` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |
| `casf2016_4m0y` | `prepared_ligand` | `prepared/4m0y_ligand` | `` | `operator_completion_required` | `prepare_vina_gnina_input_and_record_checksum` |

## Receipt Ref Plan

| Case | Field | Ref | Status | Action |
|---|---|---|---|---|
| `casf2016_4llx` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_4llx/vina_config.json` | `operator_completion_required` | `attach_vina_config_ref` |
| `casf2016_4llx` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_4llx/gnina_config.json` | `operator_completion_required` | `attach_gnina_config_ref` |
| `casf2016_4llx` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_4llx/vina_run_receipt.json` | `operator_completion_required` | `attach_vina_run_receipt_ref` |
| `casf2016_4llx` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_4llx/gnina_run_receipt.json` | `operator_completion_required` | `attach_gnina_run_receipt_ref` |
| `casf2016_4llx` | `input_preparation_provenance_ref` | `` | `operator_completion_required` | `attach_input_preparation_provenance_ref` |
| `casf2016_5c28` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_5c28/vina_config.json` | `operator_completion_required` | `attach_vina_config_ref` |
| `casf2016_5c28` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_5c28/gnina_config.json` | `operator_completion_required` | `attach_gnina_config_ref` |
| `casf2016_5c28` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_5c28/vina_run_receipt.json` | `operator_completion_required` | `attach_vina_run_receipt_ref` |
| `casf2016_5c28` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_5c28/gnina_run_receipt.json` | `operator_completion_required` | `attach_gnina_run_receipt_ref` |
| `casf2016_5c28` | `input_preparation_provenance_ref` | `` | `operator_completion_required` | `attach_input_preparation_provenance_ref` |
| `casf2016_3uuo` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_3uuo/vina_config.json` | `operator_completion_required` | `attach_vina_config_ref` |
| `casf2016_3uuo` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_3uuo/gnina_config.json` | `operator_completion_required` | `attach_gnina_config_ref` |
| `casf2016_3uuo` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3uuo/vina_run_receipt.json` | `operator_completion_required` | `attach_vina_run_receipt_ref` |
| `casf2016_3uuo` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3uuo/gnina_run_receipt.json` | `operator_completion_required` | `attach_gnina_run_receipt_ref` |
| `casf2016_3uuo` | `input_preparation_provenance_ref` | `` | `operator_completion_required` | `attach_input_preparation_provenance_ref` |
| `casf2016_3ui7` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_3ui7/vina_config.json` | `operator_completion_required` | `attach_vina_config_ref` |
| `casf2016_3ui7` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_3ui7/gnina_config.json` | `operator_completion_required` | `attach_gnina_config_ref` |
| `casf2016_3ui7` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3ui7/vina_run_receipt.json` | `operator_completion_required` | `attach_vina_run_receipt_ref` |
| `casf2016_3ui7` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3ui7/gnina_run_receipt.json` | `operator_completion_required` | `attach_gnina_run_receipt_ref` |
| `casf2016_3ui7` | `input_preparation_provenance_ref` | `` | `operator_completion_required` | `attach_input_preparation_provenance_ref` |
| `casf2016_5c2h` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_5c2h/vina_config.json` | `operator_completion_required` | `attach_vina_config_ref` |
| `casf2016_5c2h` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_5c2h/gnina_config.json` | `operator_completion_required` | `attach_gnina_config_ref` |
| `casf2016_5c2h` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_5c2h/vina_run_receipt.json` | `operator_completion_required` | `attach_vina_run_receipt_ref` |
| `casf2016_5c2h` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_5c2h/gnina_run_receipt.json` | `operator_completion_required` | `attach_gnina_run_receipt_ref` |
| `casf2016_5c2h` | `input_preparation_provenance_ref` | `` | `operator_completion_required` | `attach_input_preparation_provenance_ref` |
| `casf2016_2v00` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_2v00/vina_config.json` | `operator_completion_required` | `attach_vina_config_ref` |
| `casf2016_2v00` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_2v00/gnina_config.json` | `operator_completion_required` | `attach_gnina_config_ref` |
| `casf2016_2v00` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_2v00/vina_run_receipt.json` | `operator_completion_required` | `attach_vina_run_receipt_ref` |
| `casf2016_2v00` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_2v00/gnina_run_receipt.json` | `operator_completion_required` | `attach_gnina_run_receipt_ref` |
| `casf2016_2v00` | `input_preparation_provenance_ref` | `` | `operator_completion_required` | `attach_input_preparation_provenance_ref` |
| `casf2016_3wz8` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_3wz8/vina_config.json` | `operator_completion_required` | `attach_vina_config_ref` |
| `casf2016_3wz8` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_3wz8/gnina_config.json` | `operator_completion_required` | `attach_gnina_config_ref` |
| `casf2016_3wz8` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3wz8/vina_run_receipt.json` | `operator_completion_required` | `attach_vina_run_receipt_ref` |
| `casf2016_3wz8` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3wz8/gnina_run_receipt.json` | `operator_completion_required` | `attach_gnina_run_receipt_ref` |
| `casf2016_3wz8` | `input_preparation_provenance_ref` | `` | `operator_completion_required` | `attach_input_preparation_provenance_ref` |
| `casf2016_3pww` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_3pww/vina_config.json` | `operator_completion_required` | `attach_vina_config_ref` |
| `casf2016_3pww` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_3pww/gnina_config.json` | `operator_completion_required` | `attach_gnina_config_ref` |
| `casf2016_3pww` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3pww/vina_run_receipt.json` | `operator_completion_required` | `attach_vina_run_receipt_ref` |
| `casf2016_3pww` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3pww/gnina_run_receipt.json` | `operator_completion_required` | `attach_gnina_run_receipt_ref` |
| `casf2016_3pww` | `input_preparation_provenance_ref` | `` | `operator_completion_required` | `attach_input_preparation_provenance_ref` |
| `casf2016_3prs` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_3prs/vina_config.json` | `operator_completion_required` | `attach_vina_config_ref` |
| `casf2016_3prs` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_3prs/gnina_config.json` | `operator_completion_required` | `attach_gnina_config_ref` |
| `casf2016_3prs` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3prs/vina_run_receipt.json` | `operator_completion_required` | `attach_vina_run_receipt_ref` |
| `casf2016_3prs` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3prs/gnina_run_receipt.json` | `operator_completion_required` | `attach_gnina_run_receipt_ref` |
| `casf2016_3prs` | `input_preparation_provenance_ref` | `` | `operator_completion_required` | `attach_input_preparation_provenance_ref` |
| `casf2016_3uri` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_3uri/vina_config.json` | `operator_completion_required` | `attach_vina_config_ref` |
| `casf2016_3uri` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_3uri/gnina_config.json` | `operator_completion_required` | `attach_gnina_config_ref` |
| `casf2016_3uri` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3uri/vina_run_receipt.json` | `operator_completion_required` | `attach_vina_run_receipt_ref` |
| `casf2016_3uri` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_3uri/gnina_run_receipt.json` | `operator_completion_required` | `attach_gnina_run_receipt_ref` |
| `casf2016_3uri` | `input_preparation_provenance_ref` | `` | `operator_completion_required` | `attach_input_preparation_provenance_ref` |
| `casf2016_4m0z` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_4m0z/vina_config.json` | `operator_completion_required` | `attach_vina_config_ref` |
| `casf2016_4m0z` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_4m0z/gnina_config.json` | `operator_completion_required` | `attach_gnina_config_ref` |
| `casf2016_4m0z` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_4m0z/vina_run_receipt.json` | `operator_completion_required` | `attach_vina_run_receipt_ref` |
| `casf2016_4m0z` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_4m0z/gnina_run_receipt.json` | `operator_completion_required` | `attach_gnina_run_receipt_ref` |
| `casf2016_4m0z` | `input_preparation_provenance_ref` | `` | `operator_completion_required` | `attach_input_preparation_provenance_ref` |
| `casf2016_4m0y` | `vina_config_ref` | `operator_attached/vina_gnina/casf2016_4m0y/vina_config.json` | `operator_completion_required` | `attach_vina_config_ref` |
| `casf2016_4m0y` | `gnina_config_ref` | `operator_attached/vina_gnina/casf2016_4m0y/gnina_config.json` | `operator_completion_required` | `attach_gnina_config_ref` |
| `casf2016_4m0y` | `vina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_4m0y/vina_run_receipt.json` | `operator_completion_required` | `attach_vina_run_receipt_ref` |
| `casf2016_4m0y` | `gnina_run_receipt_ref` | `operator_attached/vina_gnina/casf2016_4m0y/gnina_run_receipt.json` | `operator_completion_required` | `attach_gnina_run_receipt_ref` |
| `casf2016_4m0y` | `input_preparation_provenance_ref` | `` | `operator_completion_required` | `attach_input_preparation_provenance_ref` |

## Commands

- `write_preflight`: `python3 scripts/build_public_benchmark_vina_gnina_input_manifest_template_preflight.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.json --out-md implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.md`
- `probe_source_urls`: `python3 scripts/build_public_benchmark_vina_gnina_input_manifest_template_preflight.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.json --out-md implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.md --probe-source-urls`
- `materialize_input_manifest_from_casf_archive`: `python3 scripts/materialize_public_benchmark_vina_gnina_input_manifest_from_casf_archive.py --archive <CASF-2016.tar.gz> --extract-dir tmp/public_benchmark_vina_gnina/casf2016_source_files --out-manifest implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest.csv --out-report implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_from_casf_archive_report.json`
- `rerun_execution_plan`: `python3 scripts/build_public_benchmark_vina_gnina_execution_plan.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_execution_plan.json`
- `rerun_runtime_readiness`: `python3 scripts/build_public_benchmark_vina_gnina_runtime_readiness.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_runtime_readiness.json`

This preflight audits the operator input-manifest template only. It does not promote the template to an actual manifest, verify license rights, run Vina/GNINA, create adapter rows, or close Public Benchmark Phase 2.
