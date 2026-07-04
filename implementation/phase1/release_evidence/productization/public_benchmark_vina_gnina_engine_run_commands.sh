#!/usr/bin/env bash
set -euo pipefail

# Generated Vina/GNINA commands. Review runtime paths before execution.
mkdir -p operator_attached/vina_gnina/casf2016_4llx
/home/betelgeuze/건축구조분석/tmp/public_benchmark_vina_gnina/bin/vina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_4llx/4llx_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_4llx/4llx_ligand.pdbqt --center_x 4.43235 --center_y 13.11385 --center_z 43.2458 --size_x 20.1159 --size_y 21.3075 --size_z 21.9792 --out operator_attached/vina_gnina/casf2016_4llx/vina_pose.sdf

mkdir -p operator_attached/vina_gnina/casf2016_4llx
/usr/bin/docker run --rm -v $PWD:/work -w /work dkoes/gnina:latest gnina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_4llx/4llx_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_4llx/4llx_ligand.pdbqt --center_x 4.43235 --center_y 13.11385 --center_z 43.2458 --size_x 20.1159 --size_y 21.3075 --size_z 21.9792 --out operator_attached/vina_gnina/casf2016_4llx/gnina_pose.sdf

mkdir -p operator_attached/vina_gnina/casf2016_5c28
/home/betelgeuze/건축구조분석/tmp/public_benchmark_vina_gnina/bin/vina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_5c28/5c28_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_5c28/5c28_ligand.pdbqt --center_x 3.85875 --center_y 12.7493 --center_z 42.1003 --size_x 19.3455 --size_y 21.8 --size_z 23.8036 --out operator_attached/vina_gnina/casf2016_5c28/vina_pose.sdf

mkdir -p operator_attached/vina_gnina/casf2016_5c28
/usr/bin/docker run --rm -v $PWD:/work -w /work dkoes/gnina:latest gnina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_5c28/5c28_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_5c28/5c28_ligand.pdbqt --center_x 3.85875 --center_y 12.7493 --center_z 42.1003 --size_x 19.3455 --size_y 21.8 --size_z 23.8036 --out operator_attached/vina_gnina/casf2016_5c28/gnina_pose.sdf

mkdir -p operator_attached/vina_gnina/casf2016_3uuo
/home/betelgeuze/건축구조분석/tmp/public_benchmark_vina_gnina/bin/vina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3uuo/3uuo_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3uuo/3uuo_ligand.pdbqt --center_x 5.19755 --center_y 12.495 --center_z 43.7852 --size_x 23.1595 --size_y 24.1588 --size_z 25.8566 --out operator_attached/vina_gnina/casf2016_3uuo/vina_pose.sdf

mkdir -p operator_attached/vina_gnina/casf2016_3uuo
/usr/bin/docker run --rm -v $PWD:/work -w /work dkoes/gnina:latest gnina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3uuo/3uuo_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3uuo/3uuo_ligand.pdbqt --center_x 5.19755 --center_y 12.495 --center_z 43.7852 --size_x 23.1595 --size_y 24.1588 --size_z 25.8566 --out operator_attached/vina_gnina/casf2016_3uuo/gnina_pose.sdf

mkdir -p operator_attached/vina_gnina/casf2016_3ui7
/home/betelgeuze/건축구조분석/tmp/public_benchmark_vina_gnina/bin/vina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3ui7/3ui7_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3ui7/3ui7_ligand.pdbqt --center_x 5.83915 --center_y 12.50425 --center_z 43.77535 --size_x 22.8429 --size_y 23.7287 --size_z 25.5305 --out operator_attached/vina_gnina/casf2016_3ui7/vina_pose.sdf

mkdir -p operator_attached/vina_gnina/casf2016_3ui7
/usr/bin/docker run --rm -v $PWD:/work -w /work dkoes/gnina:latest gnina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3ui7/3ui7_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3ui7/3ui7_ligand.pdbqt --center_x 5.83915 --center_y 12.50425 --center_z 43.77535 --size_x 22.8429 --size_y 23.7287 --size_z 25.5305 --out operator_attached/vina_gnina/casf2016_3ui7/gnina_pose.sdf

mkdir -p operator_attached/vina_gnina/casf2016_5c2h
/home/betelgeuze/건축구조분석/tmp/public_benchmark_vina_gnina/bin/vina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_5c2h/5c2h_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_5c2h/5c2h_ligand.pdbqt --center_x 4.96205 --center_y 39.55165 --center_z 57.7324 --size_x 30.3601 --size_y 26.2897 --size_z 27.6698 --out operator_attached/vina_gnina/casf2016_5c2h/vina_pose.sdf

mkdir -p operator_attached/vina_gnina/casf2016_5c2h
/usr/bin/docker run --rm -v $PWD:/work -w /work dkoes/gnina:latest gnina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_5c2h/5c2h_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_5c2h/5c2h_ligand.pdbqt --center_x 4.96205 --center_y 39.55165 --center_z 57.7324 --size_x 30.3601 --size_y 26.2897 --size_z 27.6698 --out operator_attached/vina_gnina/casf2016_5c2h/gnina_pose.sdf

mkdir -p operator_attached/vina_gnina/casf2016_2v00
/home/betelgeuze/건축구조분석/tmp/public_benchmark_vina_gnina/bin/vina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_2v00/2v00_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_2v00/2v00_ligand.pdbqt --center_x -1.7256 --center_y 2.6666 --center_z 10.71815 --size_x 25.0072 --size_y 23.7954 --size_z 20.6135 --out operator_attached/vina_gnina/casf2016_2v00/vina_pose.sdf

mkdir -p operator_attached/vina_gnina/casf2016_2v00
/usr/bin/docker run --rm -v $PWD:/work -w /work dkoes/gnina:latest gnina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_2v00/2v00_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_2v00/2v00_ligand.pdbqt --center_x -1.7256 --center_y 2.6666 --center_z 10.71815 --size_x 25.0072 --size_y 23.7954 --size_z 20.6135 --out operator_attached/vina_gnina/casf2016_2v00/gnina_pose.sdf

mkdir -p operator_attached/vina_gnina/casf2016_3wz8
/home/betelgeuze/건축구조분석/tmp/public_benchmark_vina_gnina/bin/vina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3wz8/3wz8_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3wz8/3wz8_ligand.pdbqt --center_x 23.1742 --center_y 3.68095 --center_z 58.60175 --size_x 27.2284 --size_y 31.2691 --size_z 22.4397 --out operator_attached/vina_gnina/casf2016_3wz8/vina_pose.sdf

mkdir -p operator_attached/vina_gnina/casf2016_3wz8
/usr/bin/docker run --rm -v $PWD:/work -w /work dkoes/gnina:latest gnina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3wz8/3wz8_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3wz8/3wz8_ligand.pdbqt --center_x 23.1742 --center_y 3.68095 --center_z 58.60175 --size_x 27.2284 --size_y 31.2691 --size_z 22.4397 --out operator_attached/vina_gnina/casf2016_3wz8/gnina_pose.sdf

mkdir -p operator_attached/vina_gnina/casf2016_3pww
/home/betelgeuze/건축구조분석/tmp/public_benchmark_vina_gnina/bin/vina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3pww/3pww_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3pww/3pww_ligand.pdbqt --center_x -1.9487 --center_y 4.96425 --center_z 10.0338 --size_x 30.3758 --size_y 31.4855 --size_z 27.7702 --out operator_attached/vina_gnina/casf2016_3pww/vina_pose.sdf

mkdir -p operator_attached/vina_gnina/casf2016_3pww
/usr/bin/docker run --rm -v $PWD:/work -w /work dkoes/gnina:latest gnina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3pww/3pww_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3pww/3pww_ligand.pdbqt --center_x -1.9487 --center_y 4.96425 --center_z 10.0338 --size_x 30.3758 --size_y 31.4855 --size_z 27.7702 --out operator_attached/vina_gnina/casf2016_3pww/gnina_pose.sdf

mkdir -p operator_attached/vina_gnina/casf2016_3prs
/home/betelgeuze/건축구조분석/tmp/public_benchmark_vina_gnina/bin/vina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3prs/3prs_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3prs/3prs_ligand.pdbqt --center_x -2.10335 --center_y 4.1157 --center_z 10.7508 --size_x 31.6791 --size_y 32.243 --size_z 28.9062 --out operator_attached/vina_gnina/casf2016_3prs/vina_pose.sdf

mkdir -p operator_attached/vina_gnina/casf2016_3prs
/usr/bin/docker run --rm -v $PWD:/work -w /work dkoes/gnina:latest gnina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3prs/3prs_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3prs/3prs_ligand.pdbqt --center_x -2.10335 --center_y 4.1157 --center_z 10.7508 --size_x 31.6791 --size_y 32.243 --size_z 28.9062 --out operator_attached/vina_gnina/casf2016_3prs/gnina_pose.sdf

mkdir -p operator_attached/vina_gnina/casf2016_3uri
/home/betelgeuze/건축구조분석/tmp/public_benchmark_vina_gnina/bin/vina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3uri/3uri_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3uri/3uri_ligand.pdbqt --center_x 1.84375 --center_y 31.63795 --center_z 18.57955 --size_x 31.2535 --size_y 35.0481 --size_z 32.7671 --out operator_attached/vina_gnina/casf2016_3uri/vina_pose.sdf

mkdir -p operator_attached/vina_gnina/casf2016_3uri
/usr/bin/docker run --rm -v $PWD:/work -w /work dkoes/gnina:latest gnina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3uri/3uri_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_3uri/3uri_ligand.pdbqt --center_x 1.84375 --center_y 31.63795 --center_z 18.57955 --size_x 31.2535 --size_y 35.0481 --size_z 32.7671 --out operator_attached/vina_gnina/casf2016_3uri/gnina_pose.sdf

mkdir -p operator_attached/vina_gnina/casf2016_4m0z
/home/betelgeuze/건축구조분석/tmp/public_benchmark_vina_gnina/bin/vina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_4m0z/4m0z_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_4m0z/4m0z_ligand.pdbqt --center_x -4.53895 --center_y 9.3687 --center_z 13.31405 --size_x 24.2179 --size_y 25.4252 --size_z 23.7723 --out operator_attached/vina_gnina/casf2016_4m0z/vina_pose.sdf

mkdir -p operator_attached/vina_gnina/casf2016_4m0z
/usr/bin/docker run --rm -v $PWD:/work -w /work dkoes/gnina:latest gnina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_4m0z/4m0z_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_4m0z/4m0z_ligand.pdbqt --center_x -4.53895 --center_y 9.3687 --center_z 13.31405 --size_x 24.2179 --size_y 25.4252 --size_z 23.7723 --out operator_attached/vina_gnina/casf2016_4m0z/gnina_pose.sdf

mkdir -p operator_attached/vina_gnina/casf2016_4m0y
/home/betelgeuze/건축구조분석/tmp/public_benchmark_vina_gnina/bin/vina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_4m0y/4m0y_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_4m0y/4m0y_ligand.pdbqt --center_x 6.5638 --center_y 5.39075 --center_z 22.92185 --size_x 25.8452 --size_y 24.0781 --size_z 25.2557 --out operator_attached/vina_gnina/casf2016_4m0y/vina_pose.sdf

mkdir -p operator_attached/vina_gnina/casf2016_4m0y
/usr/bin/docker run --rm -v $PWD:/work -w /work dkoes/gnina:latest gnina --receptor tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_4m0y/4m0y_receptor.pdbqt --ligand tmp/public_benchmark_vina_gnina/prepared_inputs/casf2016_4m0y/4m0y_ligand.pdbqt --center_x 6.5638 --center_y 5.39075 --center_z 22.92185 --size_x 25.8452 --size_y 24.0781 --size_z 25.2557 --out operator_attached/vina_gnina/casf2016_4m0y/gnina_pose.sdf
