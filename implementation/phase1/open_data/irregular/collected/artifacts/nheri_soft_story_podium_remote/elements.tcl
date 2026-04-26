
# truss_elements truss
element truss 1 1 2 1.0 97
element truss 2 2 3 1.0 89
element truss 3 4 3 1.0 89
element truss 4 5 2 1.0 89
element truss 5 4 5 1.0 89
element truss 6 6 3 1.0 89
element truss 7 6 7 1.0 89
element truss 8 8 6 1.0 89
element truss 9 9 6 1.0 89
element truss 10 9 10 1.0 89
element truss 11 11 4 1.0 89
element truss 12 12 11 1.0 89
element truss 13 8 4 1.0 89
element truss 14 13 8 1.0 89
element truss 15 12 8 1.0 89
element truss 16 14 13 1.0 89
element truss 17 15 9 1.0 89
element truss 18 13 9 1.0 89
element truss 19 14 15 1.0 89
element truss 20 16 5 1.0 91
element truss 21 17 13 1.0 89
element truss 22 17 12 1.0 89
element truss 23 18 12 1.0 89
element truss 24 19 17 1.0 89
element truss 25 20 17 1.0 89
element truss 26 20 18 1.0 89
element truss 27 19 14 1.0 89
element truss 28 21 14 1.0 89
element truss 29 22 19 1.0 89
element truss 30 23 20 1.0 89
element truss 31 22 20 1.0 89
element truss 32 24 19 1.0 89
element truss 33 24 21 1.0 89
element truss 34 11 16 1.0 91
element truss 35 25 10 1.0 93
element truss 36 26 15 1.0 93
element truss 37 15 25 1.0 93
element truss 38 10 27 1.0 93
element truss 39 27 28 1.0 93
element truss 40 20 29 1.0 97
element truss 41 29 12 1.0 97
element truss 42 4 1 1.0 97
element truss 43 30 4 1.0 97
element truss 44 12 30 1.0 97
element truss 45 1 31 1.0 89
element truss 46 32 1 1.0 89
element truss 47 33 1 1.0 89
element truss 48 1 34 1.0 89
element truss 49 33 35 1.0 89
element truss 50 36 27 1.0 89
element truss 51 36 35 1.0 89
element truss 52 37 33 1.0 89
element truss 53 37 36 1.0 89
element truss 54 25 36 1.0 89
element truss 55 30 32 1.0 89
element truss 56 30 33 1.0 89
element truss 57 38 37 1.0 89
element truss 58 39 30 1.0 89
element truss 59 38 30 1.0 89
element truss 60 40 37 1.0 89
element truss 61 26 40 1.0 89
element truss 62 40 25 1.0 89
element truss 63 41 38 1.0 89
element truss 64 29 38 1.0 89
element truss 65 41 40 1.0 89
element truss 66 29 39 1.0 89
element truss 67 42 29 1.0 89
element truss 68 43 29 1.0 89
element truss 69 44 41 1.0 89
element truss 70 44 26 1.0 89
element truss 71 43 41 1.0 89
element truss 72 45 44 1.0 89
element truss 73 46 44 1.0 89
element truss 74 45 43 1.0 89
element truss 75 47 42 1.0 89
element truss 76 47 43 1.0 89
element truss 77 21 26 1.0 93
element truss 78 3 31 1.0 97


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 47), with Mesh Node = 48 (auxiliary for element 79)
node 370 8000 5700 4800
rigidLink beam 225 370

# Extra nodes for zeroLength
# node tag x y z
node 371 8000 5700 4800
node 372 8000 9000 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 79 0.0 -0.0 1.0
element elasticBeamColumn 79 371 372 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 79

# zero_length_elements zeroLength
element zeroLength 1366 370 371 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1367 372 31 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 48), with Mesh Node = 49 (auxiliary for element 80)
node 373 4200 9000 4800
rigidLink beam 226 373

# Extra nodes for zeroLength
# node tag x y z
node 374 4200 9000 4800
node 375 8000 9000 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 80 0.0 0.0 1.0
element elasticBeamColumn 80 374 375 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 80

# zero_length_elements zeroLength
element zeroLength 1368 373 374 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1369 375 31 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 47), with Mesh Node = 48 (auxiliary for element 81)
node 376 8000 5500 5000
rigidLink beam 48 376
# Geometric transformation command
geomTransf PDelta 81 1.0 0.0 -0.0
element forceBeamColumn 81 376 3 81 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 49), with Mesh Node = 50 (auxiliary for element 82)
node 377 8000 9000 7900
rigidLink beam 50 377
# Geometric transformation command
geomTransf PDelta 82 1.0 0.0 -0.0
element forceBeamColumn 82 31 377 82 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 49), with Mesh Node = 50 (auxiliary for element 83)
node 378 8000 9000 8300
rigidLink beam 50 378
# Geometric transformation command
geomTransf PDelta 83 1.0 0.0 -0.0
element forceBeamColumn 83 378 33 83 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 49), with Mesh Node = 50 (auxiliary for element 84)
node 379 8000 9200 8100
rigidLink beam 227 379


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 50), with Mesh Node = 51 (auxiliary for element 84)
node 380 8000 14300 8100
rigidLink beam 228 380

# Extra nodes for zeroLength
# node tag x y z
node 381 8000 9200 8100
node 382 8000 14300 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 84 0.0 -0.0 1.0
element elasticBeamColumn 84 381 382 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 84

# zero_length_elements zeroLength
element zeroLength 1370 379 381 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1371 382 380 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 51), with Mesh Node = 52 (auxiliary for element 85)
node 383 8000 9000 14500
rigidLink beam 52 383
# Geometric transformation command
geomTransf PDelta 85 1.0 0.0 -0.0
element forceBeamColumn 85 33 383 85 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 51), with Mesh Node = 52 (auxiliary for element 86)
node 384 8000 9000 14900
rigidLink beam 52 384
# Geometric transformation command
geomTransf PDelta 86 1.0 0.0 -0.0
element forceBeamColumn 86 384 38 86 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 52), with Mesh Node = 53 (auxiliary for element 87)
node 385 4200 9000 18000
rigidLink beam 230 385

# Extra nodes for zeroLength
# node tag x y z
node 386 4200 9000 18000
node 387 8000 9000 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 87 0.0 0.0 1.0
element elasticBeamColumn 87 386 387 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 87

# zero_length_elements zeroLength
element zeroLength 1372 385 386 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1373 387 38 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 53), with Mesh Node = 54 (auxiliary for element 88)
node 388 16000 5500 5000
rigidLink beam 54 388
# Geometric transformation command
geomTransf PDelta 88 1.0 0.0 -0.0
element forceBeamColumn 88 388 7 88 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 54), with Mesh Node = 55 (auxiliary for element 89)
node 389 19800 5500 8100
rigidLink beam 232 389

# Extra nodes for zeroLength
# node tag x y z
node 390 16000 5500 8100
node 391 19800 5500 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 89 0.0 0.0 1.0
element elasticBeamColumn 89 390 391 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 89

# zero_length_elements zeroLength
element zeroLength 1374 7 390 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1375 391 389 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 55), with Mesh Node = 56 (auxiliary for element 90)
node 392 12000 5700 8100
rigidLink beam 233 392

# Extra nodes for zeroLength
# node tag x y z
node 393 12000 5700 8100
node 394 12000 9000 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 90 0.0 -0.0 1.0
element elasticBeamColumn 90 393 394 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 90

# zero_length_elements zeroLength
element zeroLength 1376 392 393 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1377 394 35 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 56), with Mesh Node = 57 (auxiliary for element 91)
node 395 16000 8800 8100
rigidLink beam 234 395

# Extra nodes for zeroLength
# node tag x y z
node 396 16000 5500 8100
node 397 16000 8800 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 91 0.0 -0.0 1.0
element elasticBeamColumn 91 396 397 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 91

# zero_length_elements zeroLength
element zeroLength 1378 7 396 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1379 397 395 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 55), with Mesh Node = 56 (auxiliary for element 92)
node 398 11800 5500 8100
rigidLink beam 233 398

# Extra nodes for zeroLength
# node tag x y z
node 399 8000 5500 8100
node 400 11800 5500 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 92 0.0 0.0 1.0
element elasticBeamColumn 92 399 400 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 92

# zero_length_elements zeroLength
element zeroLength 1380 3 399 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1381 400 398 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 54), with Mesh Node = 55 (auxiliary for element 93)
node 401 20000 5700 8100
rigidLink beam 232 401

# Extra nodes for zeroLength
# node tag x y z
node 402 20000 5700 8100
node 403 20000 9000 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 93 0.0 -0.0 1.0
element elasticBeamColumn 93 402 403 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 93

# zero_length_elements zeroLength
element zeroLength 1382 401 402 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1383 403 27 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 57), with Mesh Node = 58 (auxiliary for element 94)
node 404 12000 200 8100
rigidLink beam 235 404


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 55), with Mesh Node = 56 (auxiliary for element 94)
node 405 12000 5300 8100
rigidLink beam 233 405

# Extra nodes for zeroLength
# node tag x y z
node 406 12000 200 8100
node 407 12000 5300 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 94 0.0 -0.0 1.0
element elasticBeamColumn 94 406 407 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 94

# zero_length_elements zeroLength
element zeroLength 1384 404 406 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1385 407 405 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 56), with Mesh Node = 57 (auxiliary for element 95)
node 408 16000 9000 8300
rigidLink beam 57 408
# Geometric transformation command
geomTransf PDelta 95 1.0 0.0 -0.0
element forceBeamColumn 95 408 36 95 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 58), with Mesh Node = 59 (auxiliary for element 96)
node 409 8000 200 8100
rigidLink beam 236 409

# Extra nodes for zeroLength
# node tag x y z
node 410 8000 200 8100
node 411 8000 5500 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 96 0.0 -0.0 1.0
element elasticBeamColumn 96 410 411 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 96

# zero_length_elements zeroLength
element zeroLength 1386 409 410 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1387 411 3 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 59), with Mesh Node = 60 (auxiliary for element 97)
node 412 16000 200 8100
rigidLink beam 237 412

# Extra nodes for zeroLength
# node tag x y z
node 413 16000 200 8100
node 414 16000 5500 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 97 0.0 -0.0 1.0
element elasticBeamColumn 97 413 414 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 97

# zero_length_elements zeroLength
element zeroLength 1388 412 413 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1389 414 7 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 60), with Mesh Node = 61 (auxiliary for element 98)
node 415 16000 9000 5000
rigidLink beam 61 415


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 56), with Mesh Node = 57 (auxiliary for element 98)
node 416 16000 9000 7900
rigidLink beam 57 416
# Geometric transformation command
geomTransf PDelta 98 1.0 0.0 -0.0
element forceBeamColumn 98 415 416 98 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 61), with Mesh Node = 62 (auxiliary for element 99)
node 417 16000 9000 14500
rigidLink beam 62 417
# Geometric transformation command
geomTransf PDelta 99 1.0 0.0 -0.0
element forceBeamColumn 99 36 417 99 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 62), with Mesh Node = 63 (auxiliary for element 100)
node 418 12000 9000 11200
rigidLink beam 63 418
# Geometric transformation command
geomTransf PDelta 100 1.0 0.0 -0.0
element forceBeamColumn 100 35 418 100 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 63), with Mesh Node = 64 (auxiliary for element 101)
node 419 20000 9000 5000
rigidLink beam 64 419
# Geometric transformation command
geomTransf PDelta 101 1.0 0.0 -0.0
element forceBeamColumn 101 419 27 101 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 64), with Mesh Node = 65 (auxiliary for element 102)
node 420 20000 9000 11200
rigidLink beam 65 420
# Geometric transformation command
geomTransf PDelta 102 1.0 0.0 -0.0
element forceBeamColumn 102 27 420 102 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 65), with Mesh Node = 66 (auxiliary for element 103)
node 421 16000 14300 11400
rigidLink beam 243 421

# Extra nodes for zeroLength
# node tag x y z
node 422 16000 9000 11400
node 423 16000 14300 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 103 0.0 -0.0 1.0
element elasticBeamColumn 103 422 423 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 103

# zero_length_elements zeroLength
element zeroLength 1390 36 422 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1391 423 421 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 64), with Mesh Node = 65 (auxiliary for element 104)
node 424 20000 9200 11400
rigidLink beam 242 424


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 66), with Mesh Node = 67 (auxiliary for element 104)
node 425 20000 14300 11400
rigidLink beam 244 425

# Extra nodes for zeroLength
# node tag x y z
node 426 20000 9200 11400
node 427 20000 14300 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 104 0.0 -0.0 1.0
element elasticBeamColumn 104 426 427 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 104

# zero_length_elements zeroLength
element zeroLength 1392 424 426 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1393 427 425 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 65), with Mesh Node = 66 (auxiliary for element 105)
node 428 16000 14500 11600
rigidLink beam 66 428


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 67), with Mesh Node = 68 (auxiliary for element 105)
node 429 16000 14500 14500
rigidLink beam 68 429
# Geometric transformation command
geomTransf PDelta 105 1.0 0.0 -0.0
element forceBeamColumn 105 428 429 105 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 62), with Mesh Node = 63 (auxiliary for element 106)
node 430 12000 9200 11400
rigidLink beam 240 430


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 68), with Mesh Node = 69 (auxiliary for element 106)
node 431 12000 14300 11400
rigidLink beam 246 431

# Extra nodes for zeroLength
# node tag x y z
node 432 12000 9200 11400
node 433 12000 14300 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 106 0.0 -0.0 1.0
element elasticBeamColumn 106 432 433 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 106

# zero_length_elements zeroLength
element zeroLength 1394 430 432 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1395 433 431 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 69), with Mesh Node = 70 (auxiliary for element 107)
node 434 8000 5700 11400
rigidLink beam 247 434

# Extra nodes for zeroLength
# node tag x y z
node 435 8000 5700 11400
node 436 8000 9000 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 107 0.0 -0.0 1.0
element elasticBeamColumn 107 435 436 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 107

# zero_length_elements zeroLength
element zeroLength 1396 434 435 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1397 436 33 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 70), with Mesh Node = 71 (auxiliary for element 108)
node 437 8000 200 4800
rigidLink beam 248 437


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 47), with Mesh Node = 48 (auxiliary for element 108)
node 438 8000 5300 4800
rigidLink beam 225 438

# Extra nodes for zeroLength
# node tag x y z
node 439 8000 200 4800
node 440 8000 5300 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 108 0.0 -0.0 1.0
element elasticBeamColumn 108 439 440 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 108

# zero_length_elements zeroLength
element zeroLength 1398 437 439 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1399 440 438 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 48), with Mesh Node = 49 (auxiliary for element 109)
node 441 4000 8800 4800
rigidLink beam 226 441

# Extra nodes for zeroLength
# node tag x y z
node 442 4000 5500 4800
node 443 4000 8800 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 109 0.0 -0.0 1.0
element elasticBeamColumn 109 442 443 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 109

# zero_length_elements zeroLength
element zeroLength 1400 2 442 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1401 443 441 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 71), with Mesh Node = 72 (auxiliary for element 110)
node 444 4000 200 4800
rigidLink beam 249 444

# Extra nodes for zeroLength
# node tag x y z
node 445 4000 200 4800
node 446 4000 5500 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 110 0.0 -0.0 1.0
element elasticBeamColumn 110 445 446 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 110

# zero_length_elements zeroLength
element zeroLength 1402 444 445 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1403 446 2 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 72), with Mesh Node = 73 (auxiliary for element 111)
node 447 200 5500 4800
rigidLink beam 250 447

# Extra nodes for zeroLength
# node tag x y z
node 448 200 5500 4800
node 449 4000 5500 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 111 0.0 0.0 1.0
element elasticBeamColumn 111 448 449 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 111

# zero_length_elements zeroLength
element zeroLength 1404 447 448 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1405 449 2 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 48), with Mesh Node = 49 (auxiliary for element 112)
node 450 4000 9000 5000
rigidLink beam 49 450
# Geometric transformation command
geomTransf PDelta 112 1.0 0.0 -0.0
element forceBeamColumn 112 450 1 112 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 73), with Mesh Node = 74 (auxiliary for element 113)
node 451 4000 9000 11200
rigidLink beam 74 451
# Geometric transformation command
geomTransf PDelta 113 1.0 0.0 -0.0
element forceBeamColumn 113 1 451 113 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 73), with Mesh Node = 74 (auxiliary for element 114)
node 452 4000 9000 11600
rigidLink beam 74 452
# Geometric transformation command
geomTransf PDelta 114 1.0 0.0 -0.0
element forceBeamColumn 114 452 30 114 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 74), with Mesh Node = 75 (auxiliary for element 115)
node 453 200 9000 14700
rigidLink beam 252 453

# Extra nodes for zeroLength
# node tag x y z
node 454 200 9000 14700
node 455 4000 9000 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 115 0.0 0.0 1.0
element elasticBeamColumn 115 454 455 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 115

# zero_length_elements zeroLength
element zeroLength 1406 453 454 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1407 455 30 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 75), with Mesh Node = 76 (auxiliary for element 116)
node 456 4000 14300 14700
rigidLink beam 253 456

# Extra nodes for zeroLength
# node tag x y z
node 457 4000 9000 14700
node 458 4000 14300 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 116 0.0 -0.0 1.0
element elasticBeamColumn 116 457 458 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 116

# zero_length_elements zeroLength
element zeroLength 1408 30 457 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1409 458 456 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 76), with Mesh Node = 77 (auxiliary for element 117)
node 459 8000 14500 5000
rigidLink beam 77 459


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 50), with Mesh Node = 51 (auxiliary for element 117)
node 460 8000 14500 7900
rigidLink beam 51 460
# Geometric transformation command
geomTransf PDelta 117 1.0 0.0 -0.0
element forceBeamColumn 117 459 460 117 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 49), with Mesh Node = 50 (auxiliary for element 118)
node 461 7800 9000 8100
rigidLink beam 227 461

# Extra nodes for zeroLength
# node tag x y z
node 462 4000 9000 8100
node 463 7800 9000 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 118 0.0 0.0 1.0
element elasticBeamColumn 118 462 463 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 118

# zero_length_elements zeroLength
element zeroLength 1410 1 462 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1411 463 461 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 74), with Mesh Node = 75 (auxiliary for element 119)
node 464 0 9200 14700
rigidLink beam 252 464


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 77), with Mesh Node = 78 (auxiliary for element 119)
node 465 0 14300 14700
rigidLink beam 255 465

# Extra nodes for zeroLength
# node tag x y z
node 466 0 9200 14700
node 467 0 14300 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 119 0.0 -0.0 1.0
element elasticBeamColumn 119 466 467 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 119

# zero_length_elements zeroLength
element zeroLength 1412 464 466 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1413 467 465 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 52), with Mesh Node = 53 (auxiliary for element 120)
node 468 4000 8800 18000
rigidLink beam 230 468

# Extra nodes for zeroLength
# node tag x y z
node 469 4000 5500 18000
node 470 4000 8800 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 120 0.0 -0.0 1.0
element elasticBeamColumn 120 469 470 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 120

# zero_length_elements zeroLength
element zeroLength 1414 12 469 -mat 5 5 5 5 55 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1415 470 468 -mat 5 5 5 5 55 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 78), with Mesh Node = 79 (auxiliary for element 121)
node 471 4000 5700 14700
rigidLink beam 256 471

# Extra nodes for zeroLength
# node tag x y z
node 472 4000 5700 14700
node 473 4000 9000 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 121 0.0 -0.0 1.0
element elasticBeamColumn 121 472 473 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 121

# zero_length_elements zeroLength
element zeroLength 1416 471 472 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1417 473 30 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 79), with Mesh Node = 80 (auxiliary for element 122)
node 474 200 5500 18000
rigidLink beam 257 474

# Extra nodes for zeroLength
# node tag x y z
node 475 200 5500 18000
node 476 4000 5500 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 122 0.0 0.0 1.0
element elasticBeamColumn 122 475 476 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 122

# zero_length_elements zeroLength
element zeroLength 1418 474 475 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1419 476 12 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 51), with Mesh Node = 52 (auxiliary for element 123)
node 477 7800 9000 14700
rigidLink beam 229 477

# Extra nodes for zeroLength
# node tag x y z
node 478 4000 9000 14700
node 479 7800 9000 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 123 0.0 0.0 1.0
element elasticBeamColumn 123 478 479 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 123

# zero_length_elements zeroLength
element zeroLength 1420 30 478 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1421 479 477 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 74), with Mesh Node = 75 (auxiliary for element 124)
node 480 0 8800 14700
rigidLink beam 252 480

# Extra nodes for zeroLength
# node tag x y z
node 481 0 5500 14700
node 482 0 8800 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 124 0.0 -0.0 1.0
element elasticBeamColumn 124 481 482 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 124

# zero_length_elements zeroLength
element zeroLength 1422 11 481 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1423 482 480 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 78), with Mesh Node = 79 (auxiliary for element 125)
node 483 3800 5500 14700
rigidLink beam 256 483

# Extra nodes for zeroLength
# node tag x y z
node 484 0 5500 14700
node 485 3800 5500 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 125 0.0 0.0 1.0
element elasticBeamColumn 125 484 485 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 125

# zero_length_elements zeroLength
element zeroLength 1424 11 484 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1425 485 483 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 52), with Mesh Node = 53 (auxiliary for element 126)
node 486 3800 9000 18000
rigidLink beam 230 486

# Extra nodes for zeroLength
# node tag x y z
node 487 0 9000 18000
node 488 3800 9000 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 126 0.0 0.0 1.0
element elasticBeamColumn 126 487 488 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 126

# zero_length_elements zeroLength
element zeroLength 1426 39 487 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1427 488 486 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 52), with Mesh Node = 53 (auxiliary for element 127)
node 489 4000 9200 18000
rigidLink beam 230 489


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 80), with Mesh Node = 81 (auxiliary for element 127)
node 490 4000 14300 18000
rigidLink beam 258 490

# Extra nodes for zeroLength
# node tag x y z
node 491 4000 9200 18000
node 492 4000 14300 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 127 0.0 -0.0 1.0
element elasticBeamColumn 127 491 492 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 127

# zero_length_elements zeroLength
element zeroLength 1428 489 491 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1429 492 490 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 79), with Mesh Node = 80 (auxiliary for element 128)
node 493 0 5700 18000
rigidLink beam 257 493

# Extra nodes for zeroLength
# node tag x y z
node 494 0 5700 18000
node 495 0 9000 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 128 0.0 -0.0 1.0
element elasticBeamColumn 128 494 495 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 128

# zero_length_elements zeroLength
element zeroLength 1430 493 494 -mat 5 5 5 5 55 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1431 495 39 -mat 5 5 5 5 55 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 81), with Mesh Node = 82 (auxiliary for element 129)
node 496 0 14300 18000
rigidLink beam 259 496

# Extra nodes for zeroLength
# node tag x y z
node 497 0 9000 18000
node 498 0 14300 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 129 0.0 -0.0 1.0
element elasticBeamColumn 129 497 498 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 129

# zero_length_elements zeroLength
element zeroLength 1432 39 497 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1433 498 496 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 82), with Mesh Node = 83 (auxiliary for element 130)
node 499 8000 5700 18000
rigidLink beam 260 499

# Extra nodes for zeroLength
# node tag x y z
node 500 8000 5700 18000
node 501 8000 9000 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 130 0.0 -0.0 1.0
element elasticBeamColumn 130 500 501 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 130

# zero_length_elements zeroLength
element zeroLength 1434 499 500 -mat 5 5 5 5 55 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1435 501 38 -mat 5 5 5 5 55 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 83), with Mesh Node = 84 (auxiliary for element 131)
node 502 4000 200 14700
rigidLink beam 261 502


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 78), with Mesh Node = 79 (auxiliary for element 131)
node 503 4000 5300 14700
rigidLink beam 256 503

# Extra nodes for zeroLength
# node tag x y z
node 504 4000 200 14700
node 505 4000 5300 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 131 0.0 -0.0 1.0
element elasticBeamColumn 131 504 505 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 131

# zero_length_elements zeroLength
element zeroLength 1436 502 504 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1437 505 503 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 84), with Mesh Node = 85 (auxiliary for element 132)
node 506 8000 14300 18000
rigidLink beam 262 506

# Extra nodes for zeroLength
# node tag x y z
node 507 8000 9000 18000
node 508 8000 14300 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 132 0.0 -0.0 1.0
element elasticBeamColumn 132 507 508 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 132

# zero_length_elements zeroLength
element zeroLength 1438 38 507 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1439 508 506 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 84), with Mesh Node = 85 (auxiliary for element 133)
node 509 8200 14500 18000
rigidLink beam 262 509


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 85), with Mesh Node = 86 (auxiliary for element 133)
node 510 11800 14500 18000
rigidLink beam 263 510

# Extra nodes for zeroLength
# node tag x y z
node 511 8200 14500 18000
node 512 11800 14500 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 133 0.0 0.0 1.0
element elasticBeamColumn 133 511 512 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 133

# zero_length_elements zeroLength
element zeroLength 1440 509 511 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1441 512 510 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 82), with Mesh Node = 83 (auxiliary for element 134)
node 513 7800 5500 18000
rigidLink beam 260 513

# Extra nodes for zeroLength
# node tag x y z
node 514 4000 5500 18000
node 515 7800 5500 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 134 0.0 0.0 1.0
element elasticBeamColumn 134 514 515 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 134

# zero_length_elements zeroLength
element zeroLength 1442 12 514 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1443 515 513 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 86), with Mesh Node = 87 (auxiliary for element 135)
node 516 4000 200 18000
rigidLink beam 264 516

# Extra nodes for zeroLength
# node tag x y z
node 517 4000 200 18000
node 518 4000 5500 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 135 0.0 -0.0 1.0
element elasticBeamColumn 135 517 518 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 135

# zero_length_elements zeroLength
element zeroLength 1444 516 517 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1445 518 12 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 74), with Mesh Node = 75 (auxiliary for element 136)
node 519 0 9000 14900
rigidLink beam 75 519
# Geometric transformation command
geomTransf PDelta 136 1.0 0.0 -0.0
element forceBeamColumn 136 519 39 136 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 74), with Mesh Node = 75 (auxiliary for element 137)
node 520 0 9000 14500
rigidLink beam 75 520
# Geometric transformation command
geomTransf PDelta 137 1.0 0.0 -0.0
element forceBeamColumn 137 32 520 137 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 87), with Mesh Node = 88 (auxiliary for element 138)
node 521 0 14500 11600
rigidLink beam 88 521


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 77), with Mesh Node = 78 (auxiliary for element 138)
node 522 0 14500 14500
rigidLink beam 78 522
# Geometric transformation command
geomTransf PDelta 138 1.0 0.0 -0.0
element forceBeamColumn 138 521 522 138 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 88), with Mesh Node = 89 (auxiliary for element 139)
node 523 0 5500 11600
rigidLink beam 89 523
# Geometric transformation command
geomTransf PDelta 139 1.0 0.0 -0.0
element forceBeamColumn 139 523 11 139 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 73), with Mesh Node = 74 (auxiliary for element 140)
node 524 4000 9200 11400
rigidLink beam 251 524


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 89), with Mesh Node = 90 (auxiliary for element 140)
node 525 4000 14300 11400
rigidLink beam 267 525

# Extra nodes for zeroLength
# node tag x y z
node 526 4000 9200 11400
node 527 4000 14300 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 140 0.0 -0.0 1.0
element elasticBeamColumn 140 526 527 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 140

# zero_length_elements zeroLength
element zeroLength 1446 524 526 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1447 527 525 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 77), with Mesh Node = 78 (auxiliary for element 141)
node 528 0 14500 14900
rigidLink beam 78 528


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 81), with Mesh Node = 82 (auxiliary for element 141)
node 529 0 14500 17800
rigidLink beam 82 529
# Geometric transformation command
geomTransf PDelta 141 1.0 0.0 -0.0
element forceBeamColumn 141 528 529 141 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 48), with Mesh Node = 49 (auxiliary for element 142)
node 530 4000 9200 4800
rigidLink beam 226 530


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 90), with Mesh Node = 91 (auxiliary for element 142)
node 531 4000 14300 4800
rigidLink beam 268 531

# Extra nodes for zeroLength
# node tag x y z
node 532 4000 9200 4800
node 533 4000 14300 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 142 0.0 -0.0 1.0
element elasticBeamColumn 142 532 533 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 142

# zero_length_elements zeroLength
element zeroLength 1448 530 532 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1449 533 531 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 79), with Mesh Node = 80 (auxiliary for element 143)
node 534 0 5500 17800
rigidLink beam 80 534
# Geometric transformation command
geomTransf PDelta 143 1.0 0.0 -0.0
element forceBeamColumn 143 11 534 143 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 52), with Mesh Node = 53 (auxiliary for element 144)
node 535 4000 9000 17800
rigidLink beam 53 535
# Geometric transformation command
geomTransf PDelta 144 1.0 0.0 -0.0
element forceBeamColumn 144 30 535 144 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 47), with Mesh Node = 48 (auxiliary for element 145)
node 536 7800 5500 4800
rigidLink beam 225 536

# Extra nodes for zeroLength
# node tag x y z
node 537 4000 5500 4800
node 538 7800 5500 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 145 0.0 0.0 1.0
element elasticBeamColumn 145 537 538 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 145

# zero_length_elements zeroLength
element zeroLength 1450 2 537 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1451 538 536 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 83), with Mesh Node = 84 (auxiliary for element 146)
node 539 4000 0 14900
rigidLink beam 84 539


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 86), with Mesh Node = 87 (auxiliary for element 146)
node 540 4000 0 17800
rigidLink beam 87 540
# Geometric transformation command
geomTransf PDelta 146 1.0 0.0 -0.0
element forceBeamColumn 146 539 540 146 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 91), with Mesh Node = 92 (auxiliary for element 147)
node 541 0 200 18000
rigidLink beam 269 541


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 79), with Mesh Node = 80 (auxiliary for element 147)
node 542 0 5300 18000
rigidLink beam 257 542

# Extra nodes for zeroLength
# node tag x y z
node 543 0 200 18000
node 544 0 5300 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 147 0.0 -0.0 1.0
element elasticBeamColumn 147 543 544 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 147

# zero_length_elements zeroLength
element zeroLength 1452 541 543 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1453 544 542 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 92), with Mesh Node = 93 (auxiliary for element 148)
node 545 0 200 14700
rigidLink beam 270 545

# Extra nodes for zeroLength
# node tag x y z
node 546 0 200 14700
node 547 0 5500 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 148 0.0 -0.0 1.0
element elasticBeamColumn 148 546 547 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 148

# zero_length_elements zeroLength
element zeroLength 1454 545 546 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1455 547 11 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 91), with Mesh Node = 92 (auxiliary for element 149)
node 548 200 0 18000
rigidLink beam 269 548


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 86), with Mesh Node = 87 (auxiliary for element 149)
node 549 3800 0 18000
rigidLink beam 264 549

# Extra nodes for zeroLength
# node tag x y z
node 550 200 0 18000
node 551 3800 0 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 149 0.0 0.0 1.0
element elasticBeamColumn 149 550 551 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 149

# zero_length_elements zeroLength
element zeroLength 1456 548 550 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1457 551 549 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 86), with Mesh Node = 87 (auxiliary for element 150)
node 552 4000 0 18200
rigidLink beam 87 552


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 93), with Mesh Node = 94 (auxiliary for element 150)
node 553 4000 0 21100
rigidLink beam 94 553
# Geometric transformation command
geomTransf PDelta 150 1.0 0.0 -0.0
element forceBeamColumn 150 552 553 150 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 93), with Mesh Node = 94 (auxiliary for element 151)
node 554 4000 0 21500
rigidLink beam 94 554


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 94), with Mesh Node = 95 (auxiliary for element 151)
node 555 4000 0 24400
rigidLink beam 95 555
# Geometric transformation command
geomTransf PDelta 151 1.0 0.0 -0.0
element forceBeamColumn 151 554 555 151 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 85), with Mesh Node = 86 (auxiliary for element 152)
node 556 12000 14500 18200
rigidLink beam 86 556


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 95), with Mesh Node = 96 (auxiliary for element 152)
node 557 12000 14500 21100
rigidLink beam 96 557
# Geometric transformation command
geomTransf PDelta 152 1.0 0.0 -0.0
element forceBeamColumn 152 556 557 152 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 96), with Mesh Node = 97 (auxiliary for element 153)
node 558 8200 14500 21300
rigidLink beam 274 558


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 95), with Mesh Node = 96 (auxiliary for element 153)
node 559 11800 14500 21300
rigidLink beam 273 559

# Extra nodes for zeroLength
# node tag x y z
node 560 8200 14500 21300
node 561 11800 14500 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 153 0.0 0.0 1.0
element elasticBeamColumn 153 560 561 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 153

# zero_length_elements zeroLength
element zeroLength 1458 558 560 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1459 561 559 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 95), with Mesh Node = 96 (auxiliary for element 154)
node 562 12200 14500 21300
rigidLink beam 273 562


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 97), with Mesh Node = 98 (auxiliary for element 154)
node 563 15800 14500 21300
rigidLink beam 275 563

# Extra nodes for zeroLength
# node tag x y z
node 564 12200 14500 21300
node 565 15800 14500 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 154 0.0 0.0 1.0
element elasticBeamColumn 154 564 565 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 154

# zero_length_elements zeroLength
element zeroLength 1460 562 564 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1461 565 563 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 82), with Mesh Node = 83 (auxiliary for element 155)
node 566 8000 5500 18200
rigidLink beam 83 566
# Geometric transformation command
geomTransf PDelta 155 1.0 0.0 -0.0
element forceBeamColumn 155 566 17 155 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 98), with Mesh Node = 99 (auxiliary for element 156)
node 567 11800 5500 21300
rigidLink beam 276 567

# Extra nodes for zeroLength
# node tag x y z
node 568 8000 5500 21300
node 569 11800 5500 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 156 0.0 0.0 1.0
element elasticBeamColumn 156 568 569 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 156

# zero_length_elements zeroLength
element zeroLength 1462 17 568 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1463 569 567 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 98), with Mesh Node = 99 (auxiliary for element 157)
node 570 12000 5700 21300
rigidLink beam 276 570

# Extra nodes for zeroLength
# node tag x y z
node 571 12000 5700 21300
node 572 12000 9000 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 157 0.0 -0.0 1.0
element elasticBeamColumn 157 571 572 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 157

# zero_length_elements zeroLength
element zeroLength 1464 570 571 -mat 5 5 5 5 51 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1465 572 41 -mat 5 5 5 5 51 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 98), with Mesh Node = 99 (auxiliary for element 158)
node 573 12200 5500 21300
rigidLink beam 276 573

# Extra nodes for zeroLength
# node tag x y z
node 574 12200 5500 21300
node 575 16000 5500 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 158 0.0 0.0 1.0
element elasticBeamColumn 158 574 575 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 158

# zero_length_elements zeroLength
element zeroLength 1466 573 574 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1467 575 14 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 99), with Mesh Node = 100 (auxiliary for element 159)
node 576 12000 200 21300
rigidLink beam 277 576


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 98), with Mesh Node = 99 (auxiliary for element 159)
node 577 12000 5300 21300
rigidLink beam 276 577

# Extra nodes for zeroLength
# node tag x y z
node 578 12000 200 21300
node 579 12000 5300 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 159 0.0 -0.0 1.0
element elasticBeamColumn 159 578 579 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 159

# zero_length_elements zeroLength
element zeroLength 1468 576 578 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1469 579 577 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 100), with Mesh Node = 101 (auxiliary for element 160)
node 580 16000 200 21300
rigidLink beam 278 580

# Extra nodes for zeroLength
# node tag x y z
node 581 16000 200 21300
node 582 16000 5500 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 160 0.0 -0.0 1.0
element elasticBeamColumn 160 581 582 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 160

# zero_length_elements zeroLength
element zeroLength 1470 580 581 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1471 582 14 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 101), with Mesh Node = 102 (auxiliary for element 161)
node 583 8000 200 21300
rigidLink beam 279 583

# Extra nodes for zeroLength
# node tag x y z
node 584 8000 200 21300
node 585 8000 5500 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 161 0.0 -0.0 1.0
element elasticBeamColumn 161 584 585 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 161

# zero_length_elements zeroLength
element zeroLength 1472 583 584 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1473 585 17 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 84), with Mesh Node = 85 (auxiliary for element 162)
node 586 8000 14500 18200
rigidLink beam 85 586


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 96), with Mesh Node = 97 (auxiliary for element 162)
node 587 8000 14500 21100
rigidLink beam 97 587
# Geometric transformation command
geomTransf PDelta 162 1.0 0.0 -0.0
element forceBeamColumn 162 586 587 162 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 100), with Mesh Node = 101 (auxiliary for element 163)
node 588 16200 0 21300
rigidLink beam 278 588


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 102), with Mesh Node = 103 (auxiliary for element 163)
node 589 19800 0 21300
rigidLink beam 280 589

# Extra nodes for zeroLength
# node tag x y z
node 590 16200 0 21300
node 591 19800 0 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 163 0.0 0.0 1.0
element elasticBeamColumn 163 590 591 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 163

# zero_length_elements zeroLength
element zeroLength 1474 588 590 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1475 591 589 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 96), with Mesh Node = 97 (auxiliary for element 164)
node 592 8000 14500 21500
rigidLink beam 97 592


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 103), with Mesh Node = 104 (auxiliary for element 164)
node 593 8000 14500 24400
rigidLink beam 104 593
# Geometric transformation command
geomTransf PDelta 164 1.0 0.0 -0.0
element forceBeamColumn 164 592 593 164 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 104), with Mesh Node = 105 (auxiliary for element 165)
node 594 8200 9000 21300
rigidLink beam 282 594

# Extra nodes for zeroLength
# node tag x y z
node 595 8200 9000 21300
node 596 12000 9000 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 165 0.0 0.0 1.0
element elasticBeamColumn 165 595 596 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 165

# zero_length_elements zeroLength
element zeroLength 1476 594 595 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1477 596 41 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 105), with Mesh Node = 106 (auxiliary for element 166)
node 597 15800 9000 21300
rigidLink beam 283 597

# Extra nodes for zeroLength
# node tag x y z
node 598 12000 9000 21300
node 599 15800 9000 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 166 0.0 0.0 1.0
element elasticBeamColumn 166 598 599 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 166

# zero_length_elements zeroLength
element zeroLength 1478 41 598 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1479 599 597 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 106), with Mesh Node = 107 (auxiliary for element 167)
node 600 4200 14500 24600
rigidLink beam 284 600


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 103), with Mesh Node = 104 (auxiliary for element 167)
node 601 7800 14500 24600
rigidLink beam 281 601

# Extra nodes for zeroLength
# node tag x y z
node 602 4200 14500 24600
node 603 7800 14500 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 167 0.0 0.0 1.0
element elasticBeamColumn 167 602 603 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 167

# zero_length_elements zeroLength
element zeroLength 1480 600 602 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1481 603 601 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 104), with Mesh Node = 105 (auxiliary for element 168)
node 604 8000 9200 21300
rigidLink beam 282 604


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 96), with Mesh Node = 97 (auxiliary for element 168)
node 605 8000 14300 21300
rigidLink beam 274 605

# Extra nodes for zeroLength
# node tag x y z
node 606 8000 9200 21300
node 607 8000 14300 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 168 0.0 -0.0 1.0
element elasticBeamColumn 168 606 607 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 168

# zero_length_elements zeroLength
element zeroLength 1482 604 606 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1483 607 605 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 93), with Mesh Node = 94 (auxiliary for element 169)
node 608 4200 0 21300
rigidLink beam 271 608


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 101), with Mesh Node = 102 (auxiliary for element 169)
node 609 7800 0 21300
rigidLink beam 279 609

# Extra nodes for zeroLength
# node tag x y z
node 610 4200 0 21300
node 611 7800 0 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 169 0.0 0.0 1.0
element elasticBeamColumn 169 610 611 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 169

# zero_length_elements zeroLength
element zeroLength 1484 608 610 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1485 611 609 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 103), with Mesh Node = 104 (auxiliary for element 170)
node 612 8200 14500 24600
rigidLink beam 281 612


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 107), with Mesh Node = 108 (auxiliary for element 170)
node 613 11800 14500 24600
rigidLink beam 285 613

# Extra nodes for zeroLength
# node tag x y z
node 614 8200 14500 24600
node 615 11800 14500 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 170 0.0 0.0 1.0
element elasticBeamColumn 170 614 615 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 170

# zero_length_elements zeroLength
element zeroLength 1486 612 614 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1487 615 613 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 107), with Mesh Node = 108 (auxiliary for element 171)
node 616 12200 14500 24600
rigidLink beam 285 616


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 108), with Mesh Node = 109 (auxiliary for element 171)
node 617 15800 14500 24600
rigidLink beam 286 617

# Extra nodes for zeroLength
# node tag x y z
node 618 12200 14500 24600
node 619 15800 14500 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 171 0.0 0.0 1.0
element elasticBeamColumn 171 618 619 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 171

# zero_length_elements zeroLength
element zeroLength 1488 616 618 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1489 619 617 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 108), with Mesh Node = 109 (auxiliary for element 172)
node 620 16200 14500 24600
rigidLink beam 286 620


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 109), with Mesh Node = 110 (auxiliary for element 172)
node 621 19800 14500 24600
rigidLink beam 287 621

# Extra nodes for zeroLength
# node tag x y z
node 622 16200 14500 24600
node 623 19800 14500 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 172 0.0 0.0 1.0
element elasticBeamColumn 172 622 623 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 172

# zero_length_elements zeroLength
element zeroLength 1490 620 622 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1491 623 621 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 103), with Mesh Node = 104 (auxiliary for element 173)
node 624 8000 14300 24600
rigidLink beam 281 624

# Extra nodes for zeroLength
# node tag x y z
node 625 8000 9000 24600
node 626 8000 14300 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 173 0.0 -0.0 1.0
element elasticBeamColumn 173 625 626 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 173

# zero_length_elements zeroLength
element zeroLength 1492 43 625 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1493 626 624 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 81), with Mesh Node = 82 (auxiliary for element 174)
node 627 0 14500 18200
rigidLink beam 82 627


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 110), with Mesh Node = 111 (auxiliary for element 174)
node 628 0 14500 21100
rigidLink beam 111 628
# Geometric transformation command
geomTransf PDelta 174 1.0 0.0 -0.0
element forceBeamColumn 174 627 628 174 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 111), with Mesh Node = 112 (auxiliary for element 175)
node 629 0 9000 21100
rigidLink beam 112 629
# Geometric transformation command
geomTransf PDelta 175 1.0 0.0 -0.0
element forceBeamColumn 175 39 629 175 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 79), with Mesh Node = 80 (auxiliary for element 176)
node 630 0 5500 18200
rigidLink beam 80 630
# Geometric transformation command
geomTransf PDelta 176 1.0 0.0 -0.0
element forceBeamColumn 176 630 18 176 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 91), with Mesh Node = 92 (auxiliary for element 177)
node 631 0 0 18200
rigidLink beam 92 631


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 112), with Mesh Node = 113 (auxiliary for element 177)
node 632 0 0 21100
rigidLink beam 113 632
# Geometric transformation command
geomTransf PDelta 177 1.0 0.0 -0.0
element forceBeamColumn 177 631 632 177 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 113), with Mesh Node = 114 (auxiliary for element 178)
node 633 3800 14500 21300
rigidLink beam 291 633


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 110), with Mesh Node = 111 (auxiliary for element 178)
node 634 200 14500 21300
rigidLink beam 288 634

# Extra nodes for zeroLength
# node tag x y z
node 635 3800 14500 21300
node 636 200 14500 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 178 0.0 0.0 1.0
element elasticBeamColumn 178 635 636 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 178

# zero_length_elements zeroLength
element zeroLength 1494 633 635 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient -1.0 0.0 0.0 0.0 -1.0 0.0
element zeroLength 1495 636 634 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient -1.0 0.0 0.0 0.0 -1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 111), with Mesh Node = 112 (auxiliary for element 179)
node 637 0 9200 21300
rigidLink beam 289 637


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 110), with Mesh Node = 111 (auxiliary for element 179)
node 638 0 14300 21300
rigidLink beam 288 638

# Extra nodes for zeroLength
# node tag x y z
node 639 0 9200 21300
node 640 0 14300 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 179 0.0 -0.0 1.0
element elasticBeamColumn 179 639 640 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 179

# zero_length_elements zeroLength
element zeroLength 1496 637 639 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1497 640 638 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 111), with Mesh Node = 112 (auxiliary for element 180)
node 641 0 8800 21300
rigidLink beam 289 641

# Extra nodes for zeroLength
# node tag x y z
node 642 0 5500 21300
node 643 0 8800 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 180 0.0 -0.0 1.0
element elasticBeamColumn 180 642 643 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 180

# zero_length_elements zeroLength
element zeroLength 1498 18 642 -mat 5 5 5 5 51 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1499 643 641 -mat 5 5 5 5 51 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 104), with Mesh Node = 105 (auxiliary for element 181)
node 644 7800 9000 21300
rigidLink beam 282 644

# Extra nodes for zeroLength
# node tag x y z
node 645 4000 9000 21300
node 646 7800 9000 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 181 0.0 0.0 1.0
element elasticBeamColumn 181 645 646 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 181

# zero_length_elements zeroLength
element zeroLength 1500 29 645 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1501 646 644 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 111), with Mesh Node = 112 (auxiliary for element 182)
node 647 200 9000 21300
rigidLink beam 289 647

# Extra nodes for zeroLength
# node tag x y z
node 648 200 9000 21300
node 649 4000 9000 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 182 0.0 0.0 1.0
element elasticBeamColumn 182 648 649 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 182

# zero_length_elements zeroLength
element zeroLength 1502 647 648 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1503 649 29 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 104), with Mesh Node = 105 (auxiliary for element 183)
node 650 8000 9000 21100
rigidLink beam 105 650
# Geometric transformation command
geomTransf PDelta 183 1.0 0.0 -0.0
element forceBeamColumn 183 38 650 183 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 113), with Mesh Node = 114 (auxiliary for element 184)
node 651 4200 14500 21300
rigidLink beam 291 651


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 96), with Mesh Node = 97 (auxiliary for element 184)
node 652 7800 14500 21300
rigidLink beam 274 652

# Extra nodes for zeroLength
# node tag x y z
node 653 4200 14500 21300
node 654 7800 14500 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 184 0.0 0.0 1.0
element elasticBeamColumn 184 653 654 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 184

# zero_length_elements zeroLength
element zeroLength 1504 651 653 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1505 654 652 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 112), with Mesh Node = 113 (auxiliary for element 185)
node 655 200 0 21300
rigidLink beam 290 655


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 93), with Mesh Node = 94 (auxiliary for element 185)
node 656 3800 0 21300
rigidLink beam 271 656

# Extra nodes for zeroLength
# node tag x y z
node 657 200 0 21300
node 658 3800 0 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 185 0.0 0.0 1.0
element elasticBeamColumn 185 657 658 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 185

# zero_length_elements zeroLength
element zeroLength 1506 655 657 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1507 658 656 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 114), with Mesh Node = 115 (auxiliary for element 186)
node 659 4000 5500 21100
rigidLink beam 115 659
# Geometric transformation command
geomTransf PDelta 186 1.0 0.0 -0.0
element forceBeamColumn 186 12 659 186 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 94), with Mesh Node = 95 (auxiliary for element 187)
node 660 4000 0 24800
rigidLink beam 95 660


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 115), with Mesh Node = 116 (auxiliary for element 187)
node 661 4000 0 27700
rigidLink beam 116 661
# Geometric transformation command
geomTransf PDelta 187 1.0 0.0 -0.0
element forceBeamColumn 187 660 661 187 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 104), with Mesh Node = 105 (auxiliary for element 188)
node 662 8000 9000 21500
rigidLink beam 105 662
# Geometric transformation command
geomTransf PDelta 188 1.0 0.0 -0.0
element forceBeamColumn 188 662 43 188 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 116), with Mesh Node = 117 (auxiliary for element 189)
node 663 8000 9000 27700
rigidLink beam 117 663
# Geometric transformation command
geomTransf PDelta 189 1.0 0.0 -0.0
element forceBeamColumn 189 43 663 189 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 114), with Mesh Node = 115 (auxiliary for element 190)
node 664 4000 5500 21500
rigidLink beam 115 664
# Geometric transformation command
geomTransf PDelta 190 1.0 0.0 -0.0
element forceBeamColumn 190 664 20 190 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 117), with Mesh Node = 118 (auxiliary for element 191)
node 665 4000 5500 27700
rigidLink beam 118 665
# Geometric transformation command
geomTransf PDelta 191 1.0 0.0 -0.0
element forceBeamColumn 191 20 665 191 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 116), with Mesh Node = 117 (auxiliary for element 192)
node 666 7800 9000 27900
rigidLink beam 294 666

# Extra nodes for zeroLength
# node tag x y z
node 667 4000 9000 27900
node 668 7800 9000 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 192 0.0 0.0 1.0
element elasticBeamColumn 192 667 668 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 192

# zero_length_elements zeroLength
element zeroLength 1508 47 667 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1509 668 666 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 106), with Mesh Node = 107 (auxiliary for element 193)
node 669 3800 14500 24600
rigidLink beam 284 669


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 118), with Mesh Node = 119 (auxiliary for element 193)
node 670 200 14500 24600
rigidLink beam 296 670

# Extra nodes for zeroLength
# node tag x y z
node 671 3800 14500 24600
node 672 200 14500 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 193 0.0 0.0 1.0
element elasticBeamColumn 193 671 672 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 193

# zero_length_elements zeroLength
element zeroLength 1510 669 671 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient -1.0 0.0 0.0 0.0 -1.0 0.0
element zeroLength 1511 672 670 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient -1.0 0.0 0.0 0.0 -1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 101), with Mesh Node = 102 (auxiliary for element 194)
node 673 8000 0 21500
rigidLink beam 102 673


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 119), with Mesh Node = 120 (auxiliary for element 194)
node 674 8000 0 24400
rigidLink beam 120 674
# Geometric transformation command
geomTransf PDelta 194 1.0 0.0 -0.0
element forceBeamColumn 194 673 674 194 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 120), with Mesh Node = 121 (auxiliary for element 195)
node 675 8000 5500 24400
rigidLink beam 121 675
# Geometric transformation command
geomTransf PDelta 195 1.0 0.0 -0.0
element forceBeamColumn 195 17 675 195 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 120), with Mesh Node = 121 (auxiliary for element 196)
node 676 8000 5500 24800
rigidLink beam 121 676
# Geometric transformation command
geomTransf PDelta 196 1.0 0.0 -0.0
element forceBeamColumn 196 676 22 196 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 121), with Mesh Node = 122 (auxiliary for element 197)
node 677 12000 9000 24400
rigidLink beam 122 677
# Geometric transformation command
geomTransf PDelta 197 1.0 0.0 -0.0
element forceBeamColumn 197 41 677 197 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 122), with Mesh Node = 123 (auxiliary for element 198)
node 678 20000 14500 21500
rigidLink beam 123 678


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 109), with Mesh Node = 110 (auxiliary for element 198)
node 679 20000 14500 24400
rigidLink beam 110 679
# Geometric transformation command
geomTransf PDelta 198 1.0 0.0 -0.0
element forceBeamColumn 198 678 679 198 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 107), with Mesh Node = 108 (auxiliary for element 199)
node 680 12000 14500 24800
rigidLink beam 108 680


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 123), with Mesh Node = 124 (auxiliary for element 199)
node 681 12000 14500 27700
rigidLink beam 124 681
# Geometric transformation command
geomTransf PDelta 199 1.0 0.0 -0.0
element forceBeamColumn 199 680 681 199 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 121), with Mesh Node = 122 (auxiliary for element 200)
node 682 12000 9000 24800
rigidLink beam 122 682
# Geometric transformation command
geomTransf PDelta 200 1.0 0.0 -0.0
element forceBeamColumn 200 682 45 200 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 109), with Mesh Node = 110 (auxiliary for element 201)
node 683 20000 14500 24800
rigidLink beam 110 683


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 124), with Mesh Node = 125 (auxiliary for element 201)
node 684 20000 14500 27700
rigidLink beam 125 684
# Geometric transformation command
geomTransf PDelta 201 1.0 0.0 -0.0
element forceBeamColumn 201 683 684 201 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 125), with Mesh Node = 126 (auxiliary for element 202)
node 685 20000 14500 18200
rigidLink beam 126 685


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 122), with Mesh Node = 123 (auxiliary for element 202)
node 686 20000 14500 21100
rigidLink beam 123 686
# Geometric transformation command
geomTransf PDelta 202 1.0 0.0 -0.0
element forceBeamColumn 202 685 686 202 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 99), with Mesh Node = 100 (auxiliary for element 203)
node 687 12000 0 21500
rigidLink beam 100 687


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 126), with Mesh Node = 127 (auxiliary for element 203)
node 688 12000 0 24400
rigidLink beam 127 688
# Geometric transformation command
geomTransf PDelta 203 1.0 0.0 -0.0
element forceBeamColumn 203 687 688 203 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 126), with Mesh Node = 127 (auxiliary for element 204)
node 689 12000 0 24800
rigidLink beam 127 689


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 127), with Mesh Node = 128 (auxiliary for element 204)
node 690 12000 0 27700
rigidLink beam 128 690
# Geometric transformation command
geomTransf PDelta 204 1.0 0.0 -0.0
element forceBeamColumn 204 689 690 204 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 127), with Mesh Node = 128 (auxiliary for element 205)
node 691 12000 200 27900
rigidLink beam 305 691


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 128), with Mesh Node = 129 (auxiliary for element 205)
node 692 12000 5300 27900
rigidLink beam 306 692

# Extra nodes for zeroLength
# node tag x y z
node 693 12000 200 27900
node 694 12000 5300 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 205 0.0 -0.0 1.0
element elasticBeamColumn 205 693 694 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 205

# zero_length_elements zeroLength
element zeroLength 1512 691 693 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1513 694 692 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 100), with Mesh Node = 101 (auxiliary for element 206)
node 695 16000 0 21500
rigidLink beam 101 695


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 129), with Mesh Node = 130 (auxiliary for element 206)
node 696 16000 0 24400
rigidLink beam 130 696
# Geometric transformation command
geomTransf PDelta 206 1.0 0.0 -0.0
element forceBeamColumn 206 695 696 206 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 130), with Mesh Node = 131 (auxiliary for element 207)
node 697 8200 0 27900
rigidLink beam 308 697


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 127), with Mesh Node = 128 (auxiliary for element 207)
node 698 11800 0 27900
rigidLink beam 305 698

# Extra nodes for zeroLength
# node tag x y z
node 699 8200 0 27900
node 700 11800 0 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 207 0.0 0.0 1.0
element elasticBeamColumn 207 699 700 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 207

# zero_length_elements zeroLength
element zeroLength 1514 697 699 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1515 700 698 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 119), with Mesh Node = 120 (auxiliary for element 208)
node 701 8200 0 24600
rigidLink beam 297 701


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 126), with Mesh Node = 127 (auxiliary for element 208)
node 702 11800 0 24600
rigidLink beam 304 702

# Extra nodes for zeroLength
# node tag x y z
node 703 8200 0 24600
node 704 11800 0 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 208 0.0 0.0 1.0
element elasticBeamColumn 208 703 704 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 208

# zero_length_elements zeroLength
element zeroLength 1516 701 703 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1517 704 702 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 129), with Mesh Node = 130 (auxiliary for element 209)
node 705 16000 0 24800
rigidLink beam 130 705


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 131), with Mesh Node = 132 (auxiliary for element 209)
node 706 16000 0 27700
rigidLink beam 132 706
# Geometric transformation command
geomTransf PDelta 209 1.0 0.0 -0.0
element forceBeamColumn 209 705 706 209 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 119), with Mesh Node = 120 (auxiliary for element 210)
node 707 8000 200 24600
rigidLink beam 297 707


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 120), with Mesh Node = 121 (auxiliary for element 210)
node 708 8000 5300 24600
rigidLink beam 298 708

# Extra nodes for zeroLength
# node tag x y z
node 709 8000 200 24600
node 710 8000 5300 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 210 0.0 -0.0 1.0
element elasticBeamColumn 210 709 710 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 210

# zero_length_elements zeroLength
element zeroLength 1518 707 709 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1519 710 708 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 121), with Mesh Node = 122 (auxiliary for element 211)
node 711 12000 9200 24600
rigidLink beam 299 711


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 107), with Mesh Node = 108 (auxiliary for element 211)
node 712 12000 14300 24600
rigidLink beam 285 712

# Extra nodes for zeroLength
# node tag x y z
node 713 12000 9200 24600
node 714 12000 14300 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 211 0.0 -0.0 1.0
element elasticBeamColumn 211 713 714 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 211

# zero_length_elements zeroLength
element zeroLength 1520 711 713 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1521 714 712 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 123), with Mesh Node = 124 (auxiliary for element 212)
node 715 12200 14500 27900
rigidLink beam 301 715


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 132), with Mesh Node = 133 (auxiliary for element 212)
node 716 15800 14500 27900
rigidLink beam 310 716

# Extra nodes for zeroLength
# node tag x y z
node 717 12200 14500 27900
node 718 15800 14500 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 212 0.0 0.0 1.0
element elasticBeamColumn 212 717 718 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 212

# zero_length_elements zeroLength
element zeroLength 1522 715 717 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1523 718 716 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 123), with Mesh Node = 124 (auxiliary for element 213)
node 719 12000 14300 27900
rigidLink beam 301 719

# Extra nodes for zeroLength
# node tag x y z
node 720 12000 9000 27900
node 721 12000 14300 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 213 0.0 -0.0 1.0
element elasticBeamColumn 213 720 721 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 213

# zero_length_elements zeroLength
element zeroLength 1524 45 720 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1525 721 719 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 128), with Mesh Node = 129 (auxiliary for element 214)
node 722 11800 5500 27900
rigidLink beam 306 722

# Extra nodes for zeroLength
# node tag x y z
node 723 8000 5500 27900
node 724 11800 5500 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 214 0.0 0.0 1.0
element elasticBeamColumn 214 723 724 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 214

# zero_length_elements zeroLength
element zeroLength 1526 22 723 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1527 724 722 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 130), with Mesh Node = 131 (auxiliary for element 215)
node 725 8000 200 27900
rigidLink beam 308 725

# Extra nodes for zeroLength
# node tag x y z
node 726 8000 200 27900
node 727 8000 5500 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 215 0.0 -0.0 1.0
element elasticBeamColumn 215 726 727 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 215

# zero_length_elements zeroLength
element zeroLength 1528 725 726 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1529 727 22 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 114), with Mesh Node = 115 (auxiliary for element 216)
node 728 4200 5500 21300
rigidLink beam 292 728

# Extra nodes for zeroLength
# node tag x y z
node 729 4200 5500 21300
node 730 8000 5500 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 216 0.0 0.0 1.0
element elasticBeamColumn 216 729 730 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 216

# zero_length_elements zeroLength
element zeroLength 1530 728 729 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1531 730 17 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 119), with Mesh Node = 120 (auxiliary for element 217)
node 731 8000 0 24800
rigidLink beam 120 731


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 130), with Mesh Node = 131 (auxiliary for element 217)
node 732 8000 0 27700
rigidLink beam 131 732
# Geometric transformation command
geomTransf PDelta 217 1.0 0.0 -0.0
element forceBeamColumn 217 731 732 217 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 104), with Mesh Node = 105 (auxiliary for element 218)
node 733 8000 8800 21300
rigidLink beam 282 733

# Extra nodes for zeroLength
# node tag x y z
node 734 8000 5500 21300
node 735 8000 8800 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 218 0.0 -0.0 1.0
element elasticBeamColumn 218 734 735 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 218

# zero_length_elements zeroLength
element zeroLength 1532 17 734 -mat 5 5 5 5 51 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1533 735 733 -mat 5 5 5 5 51 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 114), with Mesh Node = 115 (auxiliary for element 219)
node 736 4000 5700 21300
rigidLink beam 292 736

# Extra nodes for zeroLength
# node tag x y z
node 737 4000 5700 21300
node 738 4000 9000 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 219 0.0 -0.0 1.0
element elasticBeamColumn 219 737 738 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 219

# zero_length_elements zeroLength
element zeroLength 1534 736 737 -mat 5 5 5 5 51 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1535 738 29 -mat 5 5 5 5 51 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 52), with Mesh Node = 53 (auxiliary for element 220)
node 739 4000 9000 18200
rigidLink beam 53 739
# Geometric transformation command
geomTransf PDelta 220 1.0 0.0 -0.0
element forceBeamColumn 220 739 29 220 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 114), with Mesh Node = 115 (auxiliary for element 221)
node 740 3800 5500 21300
rigidLink beam 292 740

# Extra nodes for zeroLength
# node tag x y z
node 741 0 5500 21300
node 742 3800 5500 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 221 0.0 0.0 1.0
element elasticBeamColumn 221 741 742 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 221

# zero_length_elements zeroLength
element zeroLength 1536 18 741 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1537 742 740 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 112), with Mesh Node = 113 (auxiliary for element 222)
node 743 0 200 21300
rigidLink beam 290 743

# Extra nodes for zeroLength
# node tag x y z
node 744 0 200 21300
node 745 0 5500 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 222 0.0 -0.0 1.0
element elasticBeamColumn 222 744 745 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 222

# zero_length_elements zeroLength
element zeroLength 1538 743 744 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1539 745 18 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 113), with Mesh Node = 114 (auxiliary for element 223)
node 746 4000 14500 21500
rigidLink beam 114 746


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 106), with Mesh Node = 107 (auxiliary for element 223)
node 747 4000 14500 24400
rigidLink beam 107 747
# Geometric transformation command
geomTransf PDelta 223 1.0 0.0 -0.0
element forceBeamColumn 223 746 747 223 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 106), with Mesh Node = 107 (auxiliary for element 224)
node 748 4000 14500 24800
rigidLink beam 107 748


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 133), with Mesh Node = 134 (auxiliary for element 224)
node 749 4000 14500 27700
rigidLink beam 134 749
# Geometric transformation command
geomTransf PDelta 224 1.0 0.0 -0.0
element forceBeamColumn 224 748 749 224 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 134), with Mesh Node = 135 (auxiliary for element 225)
node 750 4000 9000 24400
rigidLink beam 135 750
# Geometric transformation command
geomTransf PDelta 225 1.0 0.0 -0.0
element forceBeamColumn 225 29 750 225 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 134), with Mesh Node = 135 (auxiliary for element 226)
node 751 4000 9200 24600
rigidLink beam 312 751


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 106), with Mesh Node = 107 (auxiliary for element 226)
node 752 4000 14300 24600
rigidLink beam 284 752

# Extra nodes for zeroLength
# node tag x y z
node 753 4000 9200 24600
node 754 4000 14300 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 226 0.0 -0.0 1.0
element elasticBeamColumn 226 753 754 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 226

# zero_length_elements zeroLength
element zeroLength 1540 751 753 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1541 754 752 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 80), with Mesh Node = 81 (auxiliary for element 227)
node 755 4000 14500 18200
rigidLink beam 81 755


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 113), with Mesh Node = 114 (auxiliary for element 227)
node 756 4000 14500 21100
rigidLink beam 114 756
# Geometric transformation command
geomTransf PDelta 227 1.0 0.0 -0.0
element forceBeamColumn 227 755 756 227 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 134), with Mesh Node = 135 (auxiliary for element 228)
node 757 3800 9000 24600
rigidLink beam 312 757

# Extra nodes for zeroLength
# node tag x y z
node 758 0 9000 24600
node 759 3800 9000 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 228 0.0 0.0 1.0
element elasticBeamColumn 228 758 759 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 228

# zero_length_elements zeroLength
element zeroLength 1542 42 758 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1543 759 757 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 118), with Mesh Node = 119 (auxiliary for element 229)
node 760 0 14300 24600
rigidLink beam 296 760

# Extra nodes for zeroLength
# node tag x y z
node 761 0 9000 24600
node 762 0 14300 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 229 0.0 -0.0 1.0
element elasticBeamColumn 229 761 762 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 229

# zero_length_elements zeroLength
element zeroLength 1544 42 761 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1545 762 760 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 134), with Mesh Node = 135 (auxiliary for element 230)
node 763 4200 9000 24600
rigidLink beam 312 763

# Extra nodes for zeroLength
# node tag x y z
node 764 4200 9000 24600
node 765 8000 9000 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 230 0.0 0.0 1.0
element elasticBeamColumn 230 764 765 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 230

# zero_length_elements zeroLength
element zeroLength 1546 763 764 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1547 765 43 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 117), with Mesh Node = 118 (auxiliary for element 231)
node 766 4000 5700 27900
rigidLink beam 295 766

# Extra nodes for zeroLength
# node tag x y z
node 767 4000 5700 27900
node 768 4000 9000 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 231 0.0 -0.0 1.0
element elasticBeamColumn 231 767 768 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 231

# zero_length_elements zeroLength
element zeroLength 1548 766 767 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1549 768 47 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 117), with Mesh Node = 118 (auxiliary for element 232)
node 769 3800 5500 27900
rigidLink beam 295 769

# Extra nodes for zeroLength
# node tag x y z
node 770 0 5500 27900
node 771 3800 5500 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 232 0.0 0.0 1.0
element elasticBeamColumn 232 770 771 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 232

# zero_length_elements zeroLength
element zeroLength 1550 23 770 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1551 771 769 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 135), with Mesh Node = 136 (auxiliary for element 233)
node 772 200 5500 24600
rigidLink beam 313 772

# Extra nodes for zeroLength
# node tag x y z
node 773 200 5500 24600
node 774 4000 5500 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 233 0.0 0.0 1.0
element elasticBeamColumn 233 773 774 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 233

# zero_length_elements zeroLength
element zeroLength 1552 772 773 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1553 774 20 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 134), with Mesh Node = 135 (auxiliary for element 234)
node 775 4000 8800 24600
rigidLink beam 312 775

# Extra nodes for zeroLength
# node tag x y z
node 776 4000 5500 24600
node 777 4000 8800 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 234 0.0 -0.0 1.0
element elasticBeamColumn 234 776 777 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 234

# zero_length_elements zeroLength
element zeroLength 1554 20 776 -mat 5 5 5 5 53 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1555 777 775 -mat 5 5 5 5 53 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 135), with Mesh Node = 136 (auxiliary for element 235)
node 778 0 5700 24600
rigidLink beam 313 778

# Extra nodes for zeroLength
# node tag x y z
node 779 0 5700 24600
node 780 0 9000 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 235 0.0 -0.0 1.0
element elasticBeamColumn 235 779 780 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 235

# zero_length_elements zeroLength
element zeroLength 1556 778 779 -mat 5 5 5 5 53 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1557 780 42 -mat 5 5 5 5 53 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 136), with Mesh Node = 137 (auxiliary for element 236)
node 781 200 0 24600
rigidLink beam 314 781


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 94), with Mesh Node = 95 (auxiliary for element 236)
node 782 3800 0 24600
rigidLink beam 272 782

# Extra nodes for zeroLength
# node tag x y z
node 783 200 0 24600
node 784 3800 0 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 236 0.0 0.0 1.0
element elasticBeamColumn 236 783 784 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 236

# zero_length_elements zeroLength
element zeroLength 1558 781 783 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1559 784 782 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 137), with Mesh Node = 138 (auxiliary for element 237)
node 785 200 9000 27900
rigidLink beam 315 785

# Extra nodes for zeroLength
# node tag x y z
node 786 200 9000 27900
node 787 4000 9000 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 237 0.0 0.0 1.0
element elasticBeamColumn 237 786 787 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 237

# zero_length_elements zeroLength
element zeroLength 1560 785 786 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1561 787 47 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 133), with Mesh Node = 134 (auxiliary for element 238)
node 788 3800 14500 27900
rigidLink beam 311 788


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 138), with Mesh Node = 139 (auxiliary for element 238)
node 789 200 14500 27900
rigidLink beam 316 789

# Extra nodes for zeroLength
# node tag x y z
node 790 3800 14500 27900
node 791 200 14500 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 238 0.0 0.0 1.0
element elasticBeamColumn 238 790 791 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 238

# zero_length_elements zeroLength
element zeroLength 1562 788 790 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient -1.0 0.0 0.0 0.0 -1.0 0.0
element zeroLength 1563 791 789 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient -1.0 0.0 0.0 0.0 -1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 133), with Mesh Node = 134 (auxiliary for element 239)
node 792 4200 14500 27900
rigidLink beam 311 792


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 139), with Mesh Node = 140 (auxiliary for element 239)
node 793 7800 14500 27900
rigidLink beam 317 793

# Extra nodes for zeroLength
# node tag x y z
node 794 4200 14500 27900
node 795 7800 14500 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 239 0.0 0.0 1.0
element elasticBeamColumn 239 794 795 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 239

# zero_length_elements zeroLength
element zeroLength 1564 792 794 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1565 795 793 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 133), with Mesh Node = 134 (auxiliary for element 240)
node 796 4000 14300 27900
rigidLink beam 311 796

# Extra nodes for zeroLength
# node tag x y z
node 797 4000 9000 27900
node 798 4000 14300 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 240 0.0 -0.0 1.0
element elasticBeamColumn 240 797 798 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 240

# zero_length_elements zeroLength
element zeroLength 1566 47 797 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1567 798 796 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 137), with Mesh Node = 138 (auxiliary for element 241)
node 799 0 9200 27900
rigidLink beam 315 799


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 138), with Mesh Node = 139 (auxiliary for element 241)
node 800 0 14300 27900
rigidLink beam 316 800

# Extra nodes for zeroLength
# node tag x y z
node 801 0 9200 27900
node 802 0 14300 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 241 0.0 -0.0 1.0
element elasticBeamColumn 241 801 802 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 241

# zero_length_elements zeroLength
element zeroLength 1568 799 801 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1569 802 800 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 93), with Mesh Node = 94 (auxiliary for element 242)
node 803 4000 200 21300
rigidLink beam 271 803


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 114), with Mesh Node = 115 (auxiliary for element 242)
node 804 4000 5300 21300
rigidLink beam 292 804

# Extra nodes for zeroLength
# node tag x y z
node 805 4000 200 21300
node 806 4000 5300 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 242 0.0 -0.0 1.0
element elasticBeamColumn 242 805 806 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 242

# zero_length_elements zeroLength
element zeroLength 1570 803 805 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1571 806 804 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 137), with Mesh Node = 138 (auxiliary for element 243)
node 807 0 8800 27900
rigidLink beam 315 807

# Extra nodes for zeroLength
# node tag x y z
node 808 0 5500 27900
node 809 0 8800 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 243 0.0 -0.0 1.0
element elasticBeamColumn 243 808 809 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 243

# zero_length_elements zeroLength
element zeroLength 1572 23 808 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1573 809 807 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 94), with Mesh Node = 95 (auxiliary for element 244)
node 810 4200 0 24600
rigidLink beam 272 810


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 119), with Mesh Node = 120 (auxiliary for element 244)
node 811 7800 0 24600
rigidLink beam 297 811

# Extra nodes for zeroLength
# node tag x y z
node 812 4200 0 24600
node 813 7800 0 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 244 0.0 0.0 1.0
element elasticBeamColumn 244 812 813 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 244

# zero_length_elements zeroLength
element zeroLength 1574 810 812 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1575 813 811 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 94), with Mesh Node = 95 (auxiliary for element 245)
node 814 4000 200 24600
rigidLink beam 272 814

# Extra nodes for zeroLength
# node tag x y z
node 815 4000 200 24600
node 816 4000 5500 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 245 0.0 -0.0 1.0
element elasticBeamColumn 245 815 816 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 245

# zero_length_elements zeroLength
element zeroLength 1576 814 815 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1577 816 20 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 116), with Mesh Node = 117 (auxiliary for element 246)
node 817 8000 9200 27900
rigidLink beam 294 817


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 139), with Mesh Node = 140 (auxiliary for element 246)
node 818 8000 14300 27900
rigidLink beam 317 818

# Extra nodes for zeroLength
# node tag x y z
node 819 8000 9200 27900
node 820 8000 14300 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 246 0.0 -0.0 1.0
element elasticBeamColumn 246 819 820 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 246

# zero_length_elements zeroLength
element zeroLength 1578 817 819 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1579 820 818 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 116), with Mesh Node = 117 (auxiliary for element 247)
node 821 8000 8800 27900
rigidLink beam 294 821

# Extra nodes for zeroLength
# node tag x y z
node 822 8000 5500 27900
node 823 8000 8800 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 247 0.0 -0.0 1.0
element elasticBeamColumn 247 822 823 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 247

# zero_length_elements zeroLength
element zeroLength 1580 22 822 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1581 823 821 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 139), with Mesh Node = 140 (auxiliary for element 248)
node 824 8200 14500 27900
rigidLink beam 317 824


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 123), with Mesh Node = 124 (auxiliary for element 248)
node 825 11800 14500 27900
rigidLink beam 301 825

# Extra nodes for zeroLength
# node tag x y z
node 826 8200 14500 27900
node 827 11800 14500 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 248 0.0 0.0 1.0
element elasticBeamColumn 248 826 827 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 248

# zero_length_elements zeroLength
element zeroLength 1582 824 826 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1583 827 825 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 117), with Mesh Node = 118 (auxiliary for element 249)
node 828 4200 5500 27900
rigidLink beam 295 828

# Extra nodes for zeroLength
# node tag x y z
node 829 4200 5500 27900
node 830 8000 5500 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 249 0.0 0.0 1.0
element elasticBeamColumn 249 829 830 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 249

# zero_length_elements zeroLength
element zeroLength 1584 828 829 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1585 830 22 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 115), with Mesh Node = 116 (auxiliary for element 250)
node 831 4200 0 27900
rigidLink beam 293 831


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 130), with Mesh Node = 131 (auxiliary for element 250)
node 832 7800 0 27900
rigidLink beam 308 832

# Extra nodes for zeroLength
# node tag x y z
node 833 4200 0 27900
node 834 7800 0 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 250 0.0 0.0 1.0
element elasticBeamColumn 250 833 834 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 250

# zero_length_elements zeroLength
element zeroLength 1586 831 833 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1587 834 832 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 115), with Mesh Node = 116 (auxiliary for element 251)
node 835 4000 200 27900
rigidLink beam 293 835


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 117), with Mesh Node = 118 (auxiliary for element 251)
node 836 4000 5300 27900
rigidLink beam 295 836

# Extra nodes for zeroLength
# node tag x y z
node 837 4000 200 27900
node 838 4000 5300 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 251 0.0 -0.0 1.0
element elasticBeamColumn 251 837 838 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 251

# zero_length_elements zeroLength
element zeroLength 1588 835 837 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1589 838 836 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 111), with Mesh Node = 112 (auxiliary for element 252)
node 839 0 9000 21500
rigidLink beam 112 839
# Geometric transformation command
geomTransf PDelta 252 1.0 0.0 -0.0
element forceBeamColumn 252 839 42 252 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 110), with Mesh Node = 111 (auxiliary for element 253)
node 840 0 14500 21500
rigidLink beam 111 840


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 118), with Mesh Node = 119 (auxiliary for element 253)
node 841 0 14500 24400
rigidLink beam 119 841
# Geometric transformation command
geomTransf PDelta 253 1.0 0.0 -0.0
element forceBeamColumn 253 840 841 253 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 137), with Mesh Node = 138 (auxiliary for element 254)
node 842 0 9000 27700
rigidLink beam 138 842
# Geometric transformation command
geomTransf PDelta 254 1.0 0.0 -0.0
element forceBeamColumn 254 42 842 254 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 135), with Mesh Node = 136 (auxiliary for element 255)
node 843 0 5500 24400
rigidLink beam 136 843
# Geometric transformation command
geomTransf PDelta 255 1.0 0.0 -0.0
element forceBeamColumn 255 18 843 255 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 112), with Mesh Node = 113 (auxiliary for element 256)
node 844 0 0 21500
rigidLink beam 113 844


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 136), with Mesh Node = 137 (auxiliary for element 256)
node 845 0 0 24400
rigidLink beam 137 845
# Geometric transformation command
geomTransf PDelta 256 1.0 0.0 -0.0
element forceBeamColumn 256 844 845 256 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 113), with Mesh Node = 114 (auxiliary for element 257)
node 846 4000 14300 21300
rigidLink beam 291 846

# Extra nodes for zeroLength
# node tag x y z
node 847 4000 9000 21300
node 848 4000 14300 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 257 0.0 -0.0 1.0
element elasticBeamColumn 257 847 848 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 257

# zero_length_elements zeroLength
element zeroLength 1590 29 847 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1591 848 846 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 118), with Mesh Node = 119 (auxiliary for element 258)
node 849 0 14500 24800
rigidLink beam 119 849


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 138), with Mesh Node = 139 (auxiliary for element 258)
node 850 0 14500 27700
rigidLink beam 139 850
# Geometric transformation command
geomTransf PDelta 258 1.0 0.0 -0.0
element forceBeamColumn 258 849 850 258 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 136), with Mesh Node = 137 (auxiliary for element 259)
node 851 0 0 24800
rigidLink beam 137 851


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 140), with Mesh Node = 141 (auxiliary for element 259)
node 852 0 0 27700
rigidLink beam 141 852
# Geometric transformation command
geomTransf PDelta 259 1.0 0.0 -0.0
element forceBeamColumn 259 851 852 259 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 140), with Mesh Node = 141 (auxiliary for element 260)
node 853 0 200 27900
rigidLink beam 318 853

# Extra nodes for zeroLength
# node tag x y z
node 854 0 200 27900
node 855 0 5500 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 260 0.0 -0.0 1.0
element elasticBeamColumn 260 854 855 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 260

# zero_length_elements zeroLength
element zeroLength 1592 853 854 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1593 855 23 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 136), with Mesh Node = 137 (auxiliary for element 261)
node 856 0 200 24600
rigidLink beam 314 856


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 135), with Mesh Node = 136 (auxiliary for element 261)
node 857 0 5300 24600
rigidLink beam 313 857

# Extra nodes for zeroLength
# node tag x y z
node 858 0 200 24600
node 859 0 5300 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 261 0.0 -0.0 1.0
element elasticBeamColumn 261 858 859 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 261

# zero_length_elements zeroLength
element zeroLength 1594 856 858 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1595 859 857 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 140), with Mesh Node = 141 (auxiliary for element 262)
node 860 200 0 27900
rigidLink beam 318 860


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 115), with Mesh Node = 116 (auxiliary for element 262)
node 861 3800 0 27900
rigidLink beam 293 861

# Extra nodes for zeroLength
# node tag x y z
node 862 200 0 27900
node 863 3800 0 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 262 0.0 0.0 1.0
element elasticBeamColumn 262 862 863 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 262

# zero_length_elements zeroLength
element zeroLength 1596 860 862 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1597 863 861 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 90), with Mesh Node = 91 (auxiliary for element 263)
node 864 4000 14500 4600
rigidLink beam 91 864
# Geometric transformation command
geomTransf PDelta 263 1.0 0.0 -0.0
element forceBeamColumn 263 142 864 263 HingeRadau 6 200.0 6 200.0 7
# Geometric transformation command
geomTransf PDelta 264 1.0 0.0 -0.0
element forceBeamColumn 264 143 31 264 HingeRadau 6 200.0 6 200.0 7


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 63), with Mesh Node = 64 (auxiliary for element 265)
node 865 20000 9000 4600
rigidLink beam 64 865
# Geometric transformation command
geomTransf PDelta 265 1.0 0.0 -0.0
element forceBeamColumn 265 144 865 265 HingeRadau 6 200.0 6 200.0 7


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 60), with Mesh Node = 61 (auxiliary for element 266)
node 866 16000 9000 4600
rigidLink beam 61 866
# Geometric transformation command
geomTransf PDelta 266 1.0 0.0 -0.0
element forceBeamColumn 266 145 866 266 HingeRadau 6 200.0 6 200.0 7


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 72), with Mesh Node = 73 (auxiliary for element 267)
node 867 0 5500 4600
rigidLink beam 73 867
# Geometric transformation command
geomTransf PDelta 267 1.0 0.0 -0.0
element forceBeamColumn 267 146 867 267 HingeRadau 6 200.0 6 200.0 7
# Geometric transformation command
geomTransf PDelta 268 1.0 0.0 -0.0
element forceBeamColumn 268 147 2 268 HingeRadau 6 200.0 6 200.0 7


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 48), with Mesh Node = 49 (auxiliary for element 269)
node 868 4000 9000 4600
rigidLink beam 49 868
# Geometric transformation command
geomTransf PDelta 269 1.0 0.0 -0.0
element forceBeamColumn 269 148 868 269 HingeRadau 6 200.0 6 200.0 7


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 76), with Mesh Node = 77 (auxiliary for element 270)
node 869 8000 14500 4600
rigidLink beam 77 869
# Geometric transformation command
geomTransf PDelta 270 1.0 0.0 -0.0
element forceBeamColumn 270 149 869 270 HingeRadau 6 200.0 6 200.0 7


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 70), with Mesh Node = 71 (auxiliary for element 271)
node 870 8000 0 4600
rigidLink beam 71 870
# Geometric transformation command
geomTransf PDelta 271 1.0 0.0 -0.0
element forceBeamColumn 271 150 870 271 HingeRadau 6 200.0 6 200.0 7


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 71), with Mesh Node = 72 (auxiliary for element 272)
node 871 4000 0 4600
rigidLink beam 72 871
# Geometric transformation command
geomTransf PDelta 272 1.0 0.0 -0.0
element forceBeamColumn 272 151 871 272 HingeRadau 6 200.0 6 200.0 7


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 53), with Mesh Node = 54 (auxiliary for element 273)
node 872 16000 5500 4600
rigidLink beam 54 872
# Geometric transformation command
geomTransf PDelta 273 1.0 0.0 -0.0
element forceBeamColumn 273 152 872 273 HingeRadau 6 200.0 6 200.0 7


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 56), with Mesh Node = 57 (auxiliary for element 274)
node 873 16000 9200 8100
rigidLink beam 234 873


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 152), with Mesh Node = 153 (auxiliary for element 274)
node 874 16000 14300 8100
rigidLink beam 319 874

# Extra nodes for zeroLength
# node tag x y z
node 875 16000 9200 8100
node 876 16000 14300 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 274 0.0 -0.0 1.0
element elasticBeamColumn 274 875 876 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 274

# zero_length_elements zeroLength
element zeroLength 1598 873 875 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1599 876 874 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 153), with Mesh Node = 154 (auxiliary for element 275)
node 877 12200 14500 8100
rigidLink beam 320 877


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 152), with Mesh Node = 153 (auxiliary for element 275)
node 878 15800 14500 8100
rigidLink beam 319 878

# Extra nodes for zeroLength
# node tag x y z
node 879 12200 14500 8100
node 880 15800 14500 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 275 0.0 0.0 1.0
element elasticBeamColumn 275 879 880 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 275

# zero_length_elements zeroLength
element zeroLength 1600 877 879 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1601 880 878 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 154), with Mesh Node = 155 (auxiliary for element 276)
node 881 20000 14300 8100
rigidLink beam 321 881

# Extra nodes for zeroLength
# node tag x y z
node 882 20000 9000 8100
node 883 20000 14300 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 276 0.0 -0.0 1.0
element elasticBeamColumn 276 882 883 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 276

# zero_length_elements zeroLength
element zeroLength 1602 27 882 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1603 883 881 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 155), with Mesh Node = 156 (auxiliary for element 277)
node 884 4000 5700 8100
rigidLink beam 322 884

# Extra nodes for zeroLength
# node tag x y z
node 885 4000 5700 8100
node 886 4000 9000 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 277 0.0 -0.0 1.0
element elasticBeamColumn 277 885 886 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 277

# zero_length_elements zeroLength
element zeroLength 1604 884 885 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1605 886 1 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 156), with Mesh Node = 157 (auxiliary for element 278)
node 887 200 9000 8100
rigidLink beam 323 887

# Extra nodes for zeroLength
# node tag x y z
node 888 200 9000 8100
node 889 4000 9000 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 278 0.0 0.0 1.0
element elasticBeamColumn 278 888 889 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 278

# zero_length_elements zeroLength
element zeroLength 1606 887 888 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1607 889 1 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 152), with Mesh Node = 153 (auxiliary for element 279)
node 890 16200 14500 8100
rigidLink beam 319 890


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 154), with Mesh Node = 155 (auxiliary for element 279)
node 891 19800 14500 8100
rigidLink beam 321 891

# Extra nodes for zeroLength
# node tag x y z
node 892 16200 14500 8100
node 893 19800 14500 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 279 0.0 0.0 1.0
element elasticBeamColumn 279 892 893 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 279

# zero_length_elements zeroLength
element zeroLength 1608 890 892 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1609 893 891 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 59), with Mesh Node = 60 (auxiliary for element 280)
node 894 16000 0 8300
rigidLink beam 60 894


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 157), with Mesh Node = 158 (auxiliary for element 280)
node 895 16000 0 11200
rigidLink beam 158 895
# Geometric transformation command
geomTransf PDelta 280 1.0 0.0 -0.0
element forceBeamColumn 280 894 895 280 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 68), with Mesh Node = 69 (auxiliary for element 281)
node 896 12000 14500 11600
rigidLink beam 69 896


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 158), with Mesh Node = 159 (auxiliary for element 281)
node 897 12000 14500 14500
rigidLink beam 159 897
# Geometric transformation command
geomTransf PDelta 281 1.0 0.0 -0.0
element forceBeamColumn 281 896 897 281 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 159), with Mesh Node = 160 (auxiliary for element 282)
node 898 8200 14500 11400
rigidLink beam 326 898


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 68), with Mesh Node = 69 (auxiliary for element 282)
node 899 11800 14500 11400
rigidLink beam 246 899

# Extra nodes for zeroLength
# node tag x y z
node 900 8200 14500 11400
node 901 11800 14500 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 282 0.0 0.0 1.0
element elasticBeamColumn 282 900 901 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 282

# zero_length_elements zeroLength
element zeroLength 1610 898 900 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1611 901 899 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 65), with Mesh Node = 66 (auxiliary for element 283)
node 902 16200 14500 11400
rigidLink beam 243 902


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 66), with Mesh Node = 67 (auxiliary for element 283)
node 903 19800 14500 11400
rigidLink beam 244 903

# Extra nodes for zeroLength
# node tag x y z
node 904 16200 14500 11400
node 905 19800 14500 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 283 0.0 0.0 1.0
element elasticBeamColumn 283 904 905 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 283

# zero_length_elements zeroLength
element zeroLength 1612 902 904 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1613 905 903 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 68), with Mesh Node = 69 (auxiliary for element 284)
node 906 12200 14500 11400
rigidLink beam 246 906


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 65), with Mesh Node = 66 (auxiliary for element 284)
node 907 15800 14500 11400
rigidLink beam 243 907

# Extra nodes for zeroLength
# node tag x y z
node 908 12200 14500 11400
node 909 15800 14500 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 284 0.0 0.0 1.0
element elasticBeamColumn 284 908 909 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 284

# zero_length_elements zeroLength
element zeroLength 1614 906 908 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1615 909 907 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 57), with Mesh Node = 58 (auxiliary for element 285)
node 910 12000 0 8300
rigidLink beam 58 910


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 160), with Mesh Node = 161 (auxiliary for element 285)
node 911 12000 0 11200
rigidLink beam 161 911
# Geometric transformation command
geomTransf PDelta 285 1.0 0.0 -0.0
element forceBeamColumn 285 910 911 285 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 58), with Mesh Node = 59 (auxiliary for element 286)
node 912 8000 0 8300
rigidLink beam 59 912


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 161), with Mesh Node = 162 (auxiliary for element 286)
node 913 8000 0 11200
rigidLink beam 162 913
# Geometric transformation command
geomTransf PDelta 286 1.0 0.0 -0.0
element forceBeamColumn 286 912 913 286 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 64), with Mesh Node = 65 (auxiliary for element 287)
node 914 19800 9000 11400
rigidLink beam 242 914

# Extra nodes for zeroLength
# node tag x y z
node 915 16000 9000 11400
node 916 19800 9000 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 287 0.0 0.0 1.0
element elasticBeamColumn 287 915 916 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 287

# zero_length_elements zeroLength
element zeroLength 1616 36 915 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1617 916 914 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 162), with Mesh Node = 163 (auxiliary for element 288)
node 917 12000 9000 5000
rigidLink beam 163 917
# Geometric transformation command
geomTransf PDelta 288 1.0 0.0 -0.0
element forceBeamColumn 288 917 35 288 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 163), with Mesh Node = 164 (auxiliary for element 289)
node 918 16000 5500 11200
rigidLink beam 164 918
# Geometric transformation command
geomTransf PDelta 289 1.0 0.0 -0.0
element forceBeamColumn 289 7 918 289 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 69), with Mesh Node = 70 (auxiliary for element 290)
node 919 8000 5500 11200
rigidLink beam 70 919
# Geometric transformation command
geomTransf PDelta 290 1.0 0.0 -0.0
element forceBeamColumn 290 3 919 290 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 54), with Mesh Node = 55 (auxiliary for element 291)
node 920 20000 5500 8300
rigidLink beam 55 920
# Geometric transformation command
geomTransf PDelta 291 1.0 0.0 -0.0
element forceBeamColumn 291 920 10 291 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 55), with Mesh Node = 56 (auxiliary for element 292)
node 921 12000 5500 8300
rigidLink beam 56 921
# Geometric transformation command
geomTransf PDelta 292 1.0 0.0 -0.0
element forceBeamColumn 292 921 6 292 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 69), with Mesh Node = 70 (auxiliary for element 293)
node 922 8200 5500 11400
rigidLink beam 247 922

# Extra nodes for zeroLength
# node tag x y z
node 923 8200 5500 11400
node 924 12000 5500 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 293 0.0 0.0 1.0
element elasticBeamColumn 293 923 924 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 293

# zero_length_elements zeroLength
element zeroLength 1618 922 923 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1619 924 6 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 163), with Mesh Node = 164 (auxiliary for element 294)
node 925 16000 5500 11600
rigidLink beam 164 925
# Geometric transformation command
geomTransf PDelta 294 1.0 0.0 -0.0
element forceBeamColumn 294 925 9 294 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 164), with Mesh Node = 165 (auxiliary for element 295)
node 926 12000 5500 14500
rigidLink beam 165 926
# Geometric transformation command
geomTransf PDelta 295 1.0 0.0 -0.0
element forceBeamColumn 295 6 926 295 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 163), with Mesh Node = 164 (auxiliary for element 296)
node 927 16200 5500 11400
rigidLink beam 330 927

# Extra nodes for zeroLength
# node tag x y z
node 928 16200 5500 11400
node 929 20000 5500 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 296 0.0 0.0 1.0
element elasticBeamColumn 296 928 929 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 296

# zero_length_elements zeroLength
element zeroLength 1620 927 928 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1621 929 10 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 163), with Mesh Node = 164 (auxiliary for element 297)
node 930 16000 5700 11400
rigidLink beam 330 930

# Extra nodes for zeroLength
# node tag x y z
node 931 16000 5700 11400
node 932 16000 9000 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 297 0.0 -0.0 1.0
element elasticBeamColumn 297 931 932 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 297

# zero_length_elements zeroLength
element zeroLength 1622 930 931 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1623 932 36 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 62), with Mesh Node = 63 (auxiliary for element 298)
node 933 12000 8800 11400
rigidLink beam 240 933

# Extra nodes for zeroLength
# node tag x y z
node 934 12000 5500 11400
node 935 12000 8800 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 298 0.0 -0.0 1.0
element elasticBeamColumn 298 934 935 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 298

# zero_length_elements zeroLength
element zeroLength 1624 6 934 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1625 935 933 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 64), with Mesh Node = 65 (auxiliary for element 299)
node 936 20000 8800 11400
rigidLink beam 242 936

# Extra nodes for zeroLength
# node tag x y z
node 937 20000 5500 11400
node 938 20000 8800 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 299 0.0 -0.0 1.0
element elasticBeamColumn 299 937 938 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 299

# zero_length_elements zeroLength
element zeroLength 1626 10 937 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1627 938 936 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 163), with Mesh Node = 164 (auxiliary for element 300)
node 939 15800 5500 11400
rigidLink beam 330 939

# Extra nodes for zeroLength
# node tag x y z
node 940 12000 5500 11400
node 941 15800 5500 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 300 0.0 0.0 1.0
element elasticBeamColumn 300 940 941 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 300

# zero_length_elements zeroLength
element zeroLength 1628 6 940 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1629 941 939 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 165), with Mesh Node = 166 (auxiliary for element 301)
node 942 20000 200 11400
rigidLink beam 332 942

# Extra nodes for zeroLength
# node tag x y z
node 943 20000 200 11400
node 944 20000 5500 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 301 0.0 -0.0 1.0
element elasticBeamColumn 301 943 944 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 301

# zero_length_elements zeroLength
element zeroLength 1630 942 943 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1631 944 10 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 161), with Mesh Node = 162 (auxiliary for element 302)
node 945 8200 0 11400
rigidLink beam 328 945


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 160), with Mesh Node = 161 (auxiliary for element 302)
node 946 11800 0 11400
rigidLink beam 327 946

# Extra nodes for zeroLength
# node tag x y z
node 947 8200 0 11400
node 948 11800 0 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 302 0.0 0.0 1.0
element elasticBeamColumn 302 947 948 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 302

# zero_length_elements zeroLength
element zeroLength 1632 945 947 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1633 948 946 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 160), with Mesh Node = 161 (auxiliary for element 303)
node 949 12000 200 11400
rigidLink beam 327 949

# Extra nodes for zeroLength
# node tag x y z
node 950 12000 200 11400
node 951 12000 5500 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 303 0.0 -0.0 1.0
element elasticBeamColumn 303 950 951 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 303

# zero_length_elements zeroLength
element zeroLength 1634 949 950 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1635 951 6 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 157), with Mesh Node = 158 (auxiliary for element 304)
node 952 16000 200 11400
rigidLink beam 324 952


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 163), with Mesh Node = 164 (auxiliary for element 304)
node 953 16000 5300 11400
rigidLink beam 330 953

# Extra nodes for zeroLength
# node tag x y z
node 954 16000 200 11400
node 955 16000 5300 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 304 0.0 -0.0 1.0
element elasticBeamColumn 304 954 955 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 304

# zero_length_elements zeroLength
element zeroLength 1636 952 954 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1637 955 953 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 160), with Mesh Node = 161 (auxiliary for element 305)
node 956 12200 0 11400
rigidLink beam 327 956


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 157), with Mesh Node = 158 (auxiliary for element 305)
node 957 15800 0 11400
rigidLink beam 324 957

# Extra nodes for zeroLength
# node tag x y z
node 958 12200 0 11400
node 959 15800 0 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 305 0.0 0.0 1.0
element elasticBeamColumn 305 958 959 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 305

# zero_length_elements zeroLength
element zeroLength 1638 956 958 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1639 959 957 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 61), with Mesh Node = 62 (auxiliary for element 306)
node 960 16000 9200 14700
rigidLink beam 239 960


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 67), with Mesh Node = 68 (auxiliary for element 306)
node 961 16000 14300 14700
rigidLink beam 245 961

# Extra nodes for zeroLength
# node tag x y z
node 962 16000 9200 14700
node 963 16000 14300 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 306 0.0 -0.0 1.0
element elasticBeamColumn 306 962 963 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 306

# zero_length_elements zeroLength
element zeroLength 1640 960 962 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1641 963 961 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 61), with Mesh Node = 62 (auxiliary for element 307)
node 964 16000 8800 14700
rigidLink beam 239 964

# Extra nodes for zeroLength
# node tag x y z
node 965 16000 5500 14700
node 966 16000 8800 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 307 0.0 -0.0 1.0
element elasticBeamColumn 307 965 966 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 307

# zero_length_elements zeroLength
element zeroLength 1642 9 965 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1643 966 964 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 161), with Mesh Node = 162 (auxiliary for element 308)
node 967 8000 200 11400
rigidLink beam 328 967


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 69), with Mesh Node = 70 (auxiliary for element 308)
node 968 8000 5300 11400
rigidLink beam 247 968

# Extra nodes for zeroLength
# node tag x y z
node 969 8000 200 11400
node 970 8000 5300 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 308 0.0 -0.0 1.0
element elasticBeamColumn 308 969 970 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 308

# zero_length_elements zeroLength
element zeroLength 1644 967 969 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1645 970 968 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 164), with Mesh Node = 165 (auxiliary for element 309)
node 971 12000 5700 14700
rigidLink beam 331 971

# Extra nodes for zeroLength
# node tag x y z
node 972 12000 5700 14700
node 973 12000 9000 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 309 0.0 -0.0 1.0
element elasticBeamColumn 309 972 973 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 309

# zero_length_elements zeroLength
element zeroLength 1646 971 972 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1647 973 37 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 157), with Mesh Node = 158 (auxiliary for element 310)
node 974 16200 0 11400
rigidLink beam 324 974


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 165), with Mesh Node = 166 (auxiliary for element 310)
node 975 19800 0 11400
rigidLink beam 332 975

# Extra nodes for zeroLength
# node tag x y z
node 976 16200 0 11400
node 977 19800 0 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 310 0.0 0.0 1.0
element elasticBeamColumn 310 976 977 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 310

# zero_length_elements zeroLength
element zeroLength 1648 974 976 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1649 977 975 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 162), with Mesh Node = 163 (auxiliary for element 311)
node 978 12000 9200 4800
rigidLink beam 329 978


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 166), with Mesh Node = 167 (auxiliary for element 311)
node 979 12000 14300 4800
rigidLink beam 333 979

# Extra nodes for zeroLength
# node tag x y z
node 980 12000 9200 4800
node 981 12000 14300 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 311 0.0 -0.0 1.0
element elasticBeamColumn 311 980 981 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 311

# zero_length_elements zeroLength
element zeroLength 1650 978 980 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1651 981 979 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 164), with Mesh Node = 165 (auxiliary for element 312)
node 982 11800 5500 14700
rigidLink beam 331 982

# Extra nodes for zeroLength
# node tag x y z
node 983 8000 5500 14700
node 984 11800 5500 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 312 0.0 0.0 1.0
element elasticBeamColumn 312 983 984 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 312

# zero_length_elements zeroLength
element zeroLength 1652 8 983 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1653 984 982 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 71), with Mesh Node = 72 (auxiliary for element 313)
node 985 4200 0 4800
rigidLink beam 249 985


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 70), with Mesh Node = 71 (auxiliary for element 313)
node 986 7800 0 4800
rigidLink beam 248 986

# Extra nodes for zeroLength
# node tag x y z
node 987 4200 0 4800
node 988 7800 0 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 313 0.0 0.0 1.0
element elasticBeamColumn 313 987 988 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 313

# zero_length_elements zeroLength
element zeroLength 1654 985 987 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1655 988 986 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 70), with Mesh Node = 71 (auxiliary for element 314)
node 989 8200 0 4800
rigidLink beam 248 989


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 167), with Mesh Node = 168 (auxiliary for element 314)
node 990 11800 0 4800
rigidLink beam 334 990

# Extra nodes for zeroLength
# node tag x y z
node 991 8200 0 4800
node 992 11800 0 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 314 0.0 0.0 1.0
element elasticBeamColumn 314 991 992 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 314

# zero_length_elements zeroLength
element zeroLength 1656 989 991 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1657 992 990 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 167), with Mesh Node = 168 (auxiliary for element 315)
node 993 12000 200 4800
rigidLink beam 334 993


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 168), with Mesh Node = 169 (auxiliary for element 315)
node 994 12000 5300 4800
rigidLink beam 335 994

# Extra nodes for zeroLength
# node tag x y z
node 995 12000 200 4800
node 996 12000 5300 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 315 0.0 -0.0 1.0
element elasticBeamColumn 315 995 996 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 315

# zero_length_elements zeroLength
element zeroLength 1658 993 995 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1659 996 994 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 169), with Mesh Node = 170 (auxiliary for element 316)
node 997 0 200 4800
rigidLink beam 336 997


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 72), with Mesh Node = 73 (auxiliary for element 316)
node 998 0 5300 4800
rigidLink beam 250 998

# Extra nodes for zeroLength
# node tag x y z
node 999 0 200 4800
node 1000 0 5300 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 316 0.0 -0.0 1.0
element elasticBeamColumn 316 999 1000 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 316

# zero_length_elements zeroLength
element zeroLength 1660 997 999 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1661 1000 998 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 167), with Mesh Node = 168 (auxiliary for element 317)
node 1001 12200 0 4800
rigidLink beam 334 1001


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 170), with Mesh Node = 171 (auxiliary for element 317)
node 1002 15800 0 4800
rigidLink beam 337 1002

# Extra nodes for zeroLength
# node tag x y z
node 1003 12200 0 4800
node 1004 15800 0 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 317 0.0 0.0 1.0
element elasticBeamColumn 317 1003 1004 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 317

# zero_length_elements zeroLength
element zeroLength 1662 1001 1003 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1663 1004 1002 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 50), with Mesh Node = 51 (auxiliary for element 318)
node 1005 8000 14500 8300
rigidLink beam 51 1005


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 159), with Mesh Node = 160 (auxiliary for element 318)
node 1006 8000 14500 11200
rigidLink beam 160 1006
# Geometric transformation command
geomTransf PDelta 318 1.0 0.0 -0.0
element forceBeamColumn 318 1005 1006 318 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 169), with Mesh Node = 170 (auxiliary for element 319)
node 1007 200 0 4800
rigidLink beam 336 1007


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 71), with Mesh Node = 72 (auxiliary for element 319)
node 1008 3800 0 4800
rigidLink beam 249 1008

# Extra nodes for zeroLength
# node tag x y z
node 1009 200 0 4800
node 1010 3800 0 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 319 0.0 0.0 1.0
element elasticBeamColumn 319 1009 1010 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 319

# zero_length_elements zeroLength
element zeroLength 1664 1007 1009 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1665 1010 1008 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 171), with Mesh Node = 172 (auxiliary for element 320)
node 1011 4200 14500 8100
rigidLink beam 338 1011


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 50), with Mesh Node = 51 (auxiliary for element 320)
node 1012 7800 14500 8100
rigidLink beam 228 1012

# Extra nodes for zeroLength
# node tag x y z
node 1013 4200 14500 8100
node 1014 7800 14500 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 320 0.0 0.0 1.0
element elasticBeamColumn 320 1013 1014 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 320

# zero_length_elements zeroLength
element zeroLength 1666 1011 1013 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1667 1014 1012 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 159), with Mesh Node = 160 (auxiliary for element 321)
node 1015 8000 14500 11600
rigidLink beam 160 1015


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 172), with Mesh Node = 173 (auxiliary for element 321)
node 1016 8000 14500 14500
rigidLink beam 173 1016
# Geometric transformation command
geomTransf PDelta 321 1.0 0.0 -0.0
element forceBeamColumn 321 1015 1016 321 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 170), with Mesh Node = 171 (auxiliary for element 322)
node 1017 16000 200 4800
rigidLink beam 337 1017


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 53), with Mesh Node = 54 (auxiliary for element 322)
node 1018 16000 5300 4800
rigidLink beam 231 1018

# Extra nodes for zeroLength
# node tag x y z
node 1019 16000 200 4800
node 1020 16000 5300 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 322 0.0 -0.0 1.0
element elasticBeamColumn 322 1019 1020 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 322

# zero_length_elements zeroLength
element zeroLength 1668 1017 1019 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1669 1020 1018 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 171), with Mesh Node = 172 (auxiliary for element 323)
node 1021 4000 14300 8100
rigidLink beam 338 1021

# Extra nodes for zeroLength
# node tag x y z
node 1022 4000 9000 8100
node 1023 4000 14300 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 323 0.0 -0.0 1.0
element elasticBeamColumn 323 1022 1023 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 323

# zero_length_elements zeroLength
element zeroLength 1670 1 1022 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1671 1023 1021 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 75), with Mesh Node = 76 (auxiliary for element 324)
node 1024 4200 14500 14700
rigidLink beam 253 1024


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 172), with Mesh Node = 173 (auxiliary for element 324)
node 1025 7800 14500 14700
rigidLink beam 339 1025

# Extra nodes for zeroLength
# node tag x y z
node 1026 4200 14500 14700
node 1027 7800 14500 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 324 0.0 0.0 1.0
element elasticBeamColumn 324 1026 1027 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 324

# zero_length_elements zeroLength
element zeroLength 1672 1024 1026 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1673 1027 1025 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 56), with Mesh Node = 57 (auxiliary for element 325)
node 1028 15800 9000 8100
rigidLink beam 234 1028

# Extra nodes for zeroLength
# node tag x y z
node 1029 12000 9000 8100
node 1030 15800 9000 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 325 0.0 0.0 1.0
element elasticBeamColumn 325 1029 1030 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 325

# zero_length_elements zeroLength
element zeroLength 1674 35 1029 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1675 1030 1028 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 155), with Mesh Node = 156 (auxiliary for element 326)
node 1031 4200 5500 8100
rigidLink beam 322 1031

# Extra nodes for zeroLength
# node tag x y z
node 1032 4200 5500 8100
node 1033 8000 5500 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 326 0.0 0.0 1.0
element elasticBeamColumn 326 1032 1033 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 326

# zero_length_elements zeroLength
element zeroLength 1676 1031 1032 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1677 1033 3 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 56), with Mesh Node = 57 (auxiliary for element 327)
node 1034 16200 9000 8100
rigidLink beam 234 1034

# Extra nodes for zeroLength
# node tag x y z
node 1035 16200 9000 8100
node 1036 20000 9000 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 327 0.0 0.0 1.0
element elasticBeamColumn 327 1035 1036 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 327

# zero_length_elements zeroLength
element zeroLength 1678 1034 1035 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1679 1036 27 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 55), with Mesh Node = 56 (auxiliary for element 328)
node 1037 12200 5500 8100
rigidLink beam 233 1037

# Extra nodes for zeroLength
# node tag x y z
node 1038 12200 5500 8100
node 1039 16000 5500 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 328 0.0 0.0 1.0
element elasticBeamColumn 328 1038 1039 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 328

# zero_length_elements zeroLength
element zeroLength 1680 1037 1038 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1681 1039 7 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 50), with Mesh Node = 51 (auxiliary for element 329)
node 1040 8200 14500 8100
rigidLink beam 228 1040


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 153), with Mesh Node = 154 (auxiliary for element 329)
node 1041 11800 14500 8100
rigidLink beam 320 1041

# Extra nodes for zeroLength
# node tag x y z
node 1042 8200 14500 8100
node 1043 11800 14500 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 329 0.0 0.0 1.0
element elasticBeamColumn 329 1042 1043 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 329

# zero_length_elements zeroLength
element zeroLength 1682 1040 1042 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1683 1043 1041 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 62), with Mesh Node = 63 (auxiliary for element 330)
node 1044 11800 9000 11400
rigidLink beam 240 1044

# Extra nodes for zeroLength
# node tag x y z
node 1045 8000 9000 11400
node 1046 11800 9000 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 330 0.0 0.0 1.0
element elasticBeamColumn 330 1045 1046 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 330

# zero_length_elements zeroLength
element zeroLength 1684 33 1045 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1685 1046 1044 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 166), with Mesh Node = 167 (auxiliary for element 331)
node 1047 12200 14500 4800
rigidLink beam 333 1047


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 173), with Mesh Node = 174 (auxiliary for element 331)
node 1048 15800 14500 4800
rigidLink beam 340 1048

# Extra nodes for zeroLength
# node tag x y z
node 1049 12200 14500 4800
node 1050 15800 14500 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 331 0.0 0.0 1.0
element elasticBeamColumn 331 1049 1050 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 331

# zero_length_elements zeroLength
element zeroLength 1686 1047 1049 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1687 1050 1048 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 49), with Mesh Node = 50 (auxiliary for element 332)
node 1051 8200 9000 8100
rigidLink beam 227 1051

# Extra nodes for zeroLength
# node tag x y z
node 1052 8200 9000 8100
node 1053 12000 9000 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 332 0.0 0.0 1.0
element elasticBeamColumn 332 1052 1053 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 332

# zero_length_elements zeroLength
element zeroLength 1688 1051 1052 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1689 1053 35 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 162), with Mesh Node = 163 (auxiliary for element 333)
node 1054 12200 9000 4800
rigidLink beam 329 1054


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 60), with Mesh Node = 61 (auxiliary for element 333)
node 1055 15800 9000 4800
rigidLink beam 238 1055

# Extra nodes for zeroLength
# node tag x y z
node 1056 12200 9000 4800
node 1057 15800 9000 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 333 0.0 0.0 1.0
element elasticBeamColumn 333 1056 1057 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 333

# zero_length_elements zeroLength
element zeroLength 1690 1054 1056 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1691 1057 1055 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 62), with Mesh Node = 63 (auxiliary for element 334)
node 1058 12200 9000 11400
rigidLink beam 240 1058

# Extra nodes for zeroLength
# node tag x y z
node 1059 12200 9000 11400
node 1060 16000 9000 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 334 0.0 0.0 1.0
element elasticBeamColumn 334 1059 1060 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 334

# zero_length_elements zeroLength
element zeroLength 1692 1058 1059 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1693 1060 36 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 174), with Mesh Node = 175 (auxiliary for element 335)
node 1061 4200 0 11400
rigidLink beam 341 1061


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 161), with Mesh Node = 162 (auxiliary for element 335)
node 1062 7800 0 11400
rigidLink beam 328 1062

# Extra nodes for zeroLength
# node tag x y z
node 1063 4200 0 11400
node 1064 7800 0 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 335 0.0 0.0 1.0
element elasticBeamColumn 335 1063 1064 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 335

# zero_length_elements zeroLength
element zeroLength 1694 1061 1063 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1695 1064 1062 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 159), with Mesh Node = 160 (auxiliary for element 336)
node 1065 8000 14300 11400
rigidLink beam 326 1065

# Extra nodes for zeroLength
# node tag x y z
node 1066 8000 9000 11400
node 1067 8000 14300 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 336 0.0 -0.0 1.0
element elasticBeamColumn 336 1066 1067 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 336

# zero_length_elements zeroLength
element zeroLength 1696 33 1066 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1697 1067 1065 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 60), with Mesh Node = 61 (auxiliary for element 337)
node 1068 16000 9200 4800
rigidLink beam 238 1068


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 173), with Mesh Node = 174 (auxiliary for element 337)
node 1069 16000 14300 4800
rigidLink beam 340 1069

# Extra nodes for zeroLength
# node tag x y z
node 1070 16000 9200 4800
node 1071 16000 14300 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 337 0.0 -0.0 1.0
element elasticBeamColumn 337 1070 1071 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 337

# zero_length_elements zeroLength
element zeroLength 1698 1068 1070 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1699 1071 1069 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 63), with Mesh Node = 64 (auxiliary for element 338)
node 1072 20000 9200 4800
rigidLink beam 241 1072


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 175), with Mesh Node = 176 (auxiliary for element 338)
node 1073 20000 14300 4800
rigidLink beam 342 1073

# Extra nodes for zeroLength
# node tag x y z
node 1074 20000 9200 4800
node 1075 20000 14300 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 338 0.0 -0.0 1.0
element elasticBeamColumn 338 1074 1075 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 338

# zero_length_elements zeroLength
element zeroLength 1700 1072 1074 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1701 1075 1073 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 63), with Mesh Node = 64 (auxiliary for element 339)
node 1076 20000 8800 4800
rigidLink beam 241 1076

# Extra nodes for zeroLength
# node tag x y z
node 1077 20000 5500 4800
node 1078 20000 8800 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 339 0.0 -0.0 1.0
element elasticBeamColumn 339 1077 1078 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 339

# zero_length_elements zeroLength
element zeroLength 1702 28 1077 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1703 1078 1076 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 53), with Mesh Node = 54 (auxiliary for element 340)
node 1079 16000 5700 4800
rigidLink beam 231 1079


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 60), with Mesh Node = 61 (auxiliary for element 340)
node 1080 16000 8800 4800
rigidLink beam 238 1080

# Extra nodes for zeroLength
# node tag x y z
node 1081 16000 5700 4800
node 1082 16000 8800 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 340 0.0 -0.0 1.0
element elasticBeamColumn 340 1081 1082 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 340

# zero_length_elements zeroLength
element zeroLength 1704 1079 1081 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1705 1082 1080 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 76), with Mesh Node = 77 (auxiliary for element 341)
node 1083 8200 14500 4800
rigidLink beam 254 1083


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 166), with Mesh Node = 167 (auxiliary for element 341)
node 1084 11800 14500 4800
rigidLink beam 333 1084

# Extra nodes for zeroLength
# node tag x y z
node 1085 8200 14500 4800
node 1086 11800 14500 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 341 0.0 0.0 1.0
element elasticBeamColumn 341 1085 1086 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 341

# zero_length_elements zeroLength
element zeroLength 1706 1083 1085 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1707 1086 1084 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 60), with Mesh Node = 61 (auxiliary for element 342)
node 1087 16200 9000 4800
rigidLink beam 238 1087


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 63), with Mesh Node = 64 (auxiliary for element 342)
node 1088 19800 9000 4800
rigidLink beam 241 1088

# Extra nodes for zeroLength
# node tag x y z
node 1089 16200 9000 4800
node 1090 19800 9000 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 342 0.0 0.0 1.0
element elasticBeamColumn 342 1089 1090 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 342

# zero_length_elements zeroLength
element zeroLength 1708 1087 1089 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1709 1090 1088 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 51), with Mesh Node = 52 (auxiliary for element 343)
node 1091 8000 8800 14700
rigidLink beam 229 1091

# Extra nodes for zeroLength
# node tag x y z
node 1092 8000 5500 14700
node 1093 8000 8800 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 343 0.0 -0.0 1.0
element elasticBeamColumn 343 1092 1093 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 343

# zero_length_elements zeroLength
element zeroLength 1710 8 1092 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1711 1093 1091 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 51), with Mesh Node = 52 (auxiliary for element 344)
node 1094 8200 9000 14700
rigidLink beam 229 1094

# Extra nodes for zeroLength
# node tag x y z
node 1095 8200 9000 14700
node 1096 12000 9000 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 344 0.0 0.0 1.0
element elasticBeamColumn 344 1095 1096 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 344

# zero_length_elements zeroLength
element zeroLength 1712 1094 1095 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1713 1096 37 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 61), with Mesh Node = 62 (auxiliary for element 345)
node 1097 15800 9000 14700
rigidLink beam 239 1097

# Extra nodes for zeroLength
# node tag x y z
node 1098 12000 9000 14700
node 1099 15800 9000 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 345 0.0 0.0 1.0
element elasticBeamColumn 345 1098 1099 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 345

# zero_length_elements zeroLength
element zeroLength 1714 37 1098 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1715 1099 1097 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 172), with Mesh Node = 173 (auxiliary for element 346)
node 1100 8200 14500 14700
rigidLink beam 339 1100


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 158), with Mesh Node = 159 (auxiliary for element 346)
node 1101 11800 14500 14700
rigidLink beam 325 1101

# Extra nodes for zeroLength
# node tag x y z
node 1102 8200 14500 14700
node 1103 11800 14500 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 346 0.0 0.0 1.0
element elasticBeamColumn 346 1102 1103 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 346

# zero_length_elements zeroLength
element zeroLength 1716 1100 1102 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1717 1103 1101 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 67), with Mesh Node = 68 (auxiliary for element 347)
node 1104 16200 14500 14700
rigidLink beam 245 1104


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 176), with Mesh Node = 177 (auxiliary for element 347)
node 1105 19800 14500 14700
rigidLink beam 343 1105

# Extra nodes for zeroLength
# node tag x y z
node 1106 16200 14500 14700
node 1107 19800 14500 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 347 0.0 0.0 1.0
element elasticBeamColumn 347 1106 1107 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 347

# zero_length_elements zeroLength
element zeroLength 1718 1104 1106 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1719 1107 1105 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 61), with Mesh Node = 62 (auxiliary for element 348)
node 1108 16200 9000 14700
rigidLink beam 239 1108

# Extra nodes for zeroLength
# node tag x y z
node 1109 16200 9000 14700
node 1110 20000 9000 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 348 0.0 0.0 1.0
element elasticBeamColumn 348 1109 1110 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 348

# zero_length_elements zeroLength
element zeroLength 1720 1108 1109 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1721 1110 25 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 158), with Mesh Node = 159 (auxiliary for element 349)
node 1111 12200 14500 14700
rigidLink beam 325 1111


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 67), with Mesh Node = 68 (auxiliary for element 349)
node 1112 15800 14500 14700
rigidLink beam 245 1112

# Extra nodes for zeroLength
# node tag x y z
node 1113 12200 14500 14700
node 1114 15800 14500 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 349 0.0 0.0 1.0
element elasticBeamColumn 349 1113 1114 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 349

# zero_length_elements zeroLength
element zeroLength 1722 1111 1113 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1723 1114 1112 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 173), with Mesh Node = 174 (auxiliary for element 350)
node 1115 16000 14500 5000
rigidLink beam 174 1115


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 152), with Mesh Node = 153 (auxiliary for element 350)
node 1116 16000 14500 7900
rigidLink beam 153 1116
# Geometric transformation command
geomTransf PDelta 350 1.0 0.0 -0.0
element forceBeamColumn 350 1115 1116 350 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 78), with Mesh Node = 79 (auxiliary for element 351)
node 1117 4200 5500 14700
rigidLink beam 256 1117

# Extra nodes for zeroLength
# node tag x y z
node 1118 4200 5500 14700
node 1119 8000 5500 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 351 0.0 0.0 1.0
element elasticBeamColumn 351 1118 1119 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 351

# zero_length_elements zeroLength
element zeroLength 1724 1117 1118 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1725 1119 8 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 51), with Mesh Node = 52 (auxiliary for element 352)
node 1120 8000 9200 14700
rigidLink beam 229 1120


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 172), with Mesh Node = 173 (auxiliary for element 352)
node 1121 8000 14300 14700
rigidLink beam 339 1121

# Extra nodes for zeroLength
# node tag x y z
node 1122 8000 9200 14700
node 1123 8000 14300 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 352 0.0 -0.0 1.0
element elasticBeamColumn 352 1122 1123 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 352

# zero_length_elements zeroLength
element zeroLength 1726 1120 1122 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1727 1123 1121 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 177), with Mesh Node = 178 (auxiliary for element 353)
node 1124 11800 9000 18000
rigidLink beam 344 1124

# Extra nodes for zeroLength
# node tag x y z
node 1125 8000 9000 18000
node 1126 11800 9000 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 353 0.0 0.0 1.0
element elasticBeamColumn 353 1125 1126 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 353

# zero_length_elements zeroLength
element zeroLength 1728 38 1125 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1729 1126 1124 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 49), with Mesh Node = 50 (auxiliary for element 354)
node 1127 8000 8800 8100
rigidLink beam 227 1127

# Extra nodes for zeroLength
# node tag x y z
node 1128 8000 5500 8100
node 1129 8000 8800 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 354 0.0 -0.0 1.0
element elasticBeamColumn 354 1128 1129 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 354

# zero_length_elements zeroLength
element zeroLength 1730 3 1128 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1731 1129 1127 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 171), with Mesh Node = 172 (auxiliary for element 355)
node 1130 3800 14500 8100
rigidLink beam 338 1130


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 178), with Mesh Node = 179 (auxiliary for element 355)
node 1131 200 14500 8100
rigidLink beam 345 1131

# Extra nodes for zeroLength
# node tag x y z
node 1132 3800 14500 8100
node 1133 200 14500 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 355 0.0 0.0 1.0
element elasticBeamColumn 355 1132 1133 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 355

# zero_length_elements zeroLength
element zeroLength 1732 1130 1132 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient -1.0 0.0 0.0 0.0 -1.0 0.0
element zeroLength 1733 1133 1131 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient -1.0 0.0 0.0 0.0 -1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 88), with Mesh Node = 89 (auxiliary for element 356)
node 1134 0 5500 11200
rigidLink beam 89 1134
# Geometric transformation command
geomTransf PDelta 356 1.0 0.0 -0.0
element forceBeamColumn 356 5 1134 356 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 89), with Mesh Node = 90 (auxiliary for element 357)
node 1135 3800 14500 11400
rigidLink beam 267 1135


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 87), with Mesh Node = 88 (auxiliary for element 357)
node 1136 200 14500 11400
rigidLink beam 265 1136

# Extra nodes for zeroLength
# node tag x y z
node 1137 3800 14500 11400
node 1138 200 14500 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 357 0.0 0.0 1.0
element elasticBeamColumn 357 1137 1138 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 357

# zero_length_elements zeroLength
element zeroLength 1734 1135 1137 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient -1.0 0.0 0.0 0.0 -1.0 0.0
element zeroLength 1735 1138 1136 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient -1.0 0.0 0.0 0.0 -1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 156), with Mesh Node = 157 (auxiliary for element 358)
node 1139 0 9000 8300
rigidLink beam 157 1139
# Geometric transformation command
geomTransf PDelta 358 1.0 0.0 -0.0
element forceBeamColumn 358 1139 32 358 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 87), with Mesh Node = 88 (auxiliary for element 359)
node 1140 0 14300 11400
rigidLink beam 265 1140

# Extra nodes for zeroLength
# node tag x y z
node 1141 0 9000 11400
node 1142 0 14300 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 359 0.0 -0.0 1.0
element elasticBeamColumn 359 1141 1142 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 359

# zero_length_elements zeroLength
element zeroLength 1736 32 1141 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1737 1142 1140 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 169), with Mesh Node = 170 (auxiliary for element 360)
node 1143 0 0 5000
rigidLink beam 170 1143


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 179), with Mesh Node = 180 (auxiliary for element 360)
node 1144 0 0 7900
rigidLink beam 180 1144
# Geometric transformation command
geomTransf PDelta 360 1.0 0.0 -0.0
element forceBeamColumn 360 1143 1144 360 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 73), with Mesh Node = 74 (auxiliary for element 361)
node 1145 3800 9000 11400
rigidLink beam 251 1145

# Extra nodes for zeroLength
# node tag x y z
node 1146 0 9000 11400
node 1147 3800 9000 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 361 0.0 0.0 1.0
element elasticBeamColumn 361 1146 1147 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 361

# zero_length_elements zeroLength
element zeroLength 1738 32 1146 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1739 1147 1145 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 48), with Mesh Node = 49 (auxiliary for element 362)
node 1148 3800 9000 4800
rigidLink beam 226 1148

# Extra nodes for zeroLength
# node tag x y z
node 1149 0 9000 4800
node 1150 3800 9000 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 362 0.0 0.0 1.0
element elasticBeamColumn 362 1149 1150 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 362

# zero_length_elements zeroLength
element zeroLength 1740 34 1149 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1741 1150 1148 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 72), with Mesh Node = 73 (auxiliary for element 363)
node 1151 0 5700 4800
rigidLink beam 250 1151

# Extra nodes for zeroLength
# node tag x y z
node 1152 0 5700 4800
node 1153 0 9000 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 363 0.0 -0.0 1.0
element elasticBeamColumn 363 1152 1153 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 363

# zero_length_elements zeroLength
element zeroLength 1742 1151 1152 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1743 1153 34 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 88), with Mesh Node = 89 (auxiliary for element 364)
node 1154 0 5700 11400
rigidLink beam 266 1154

# Extra nodes for zeroLength
# node tag x y z
node 1155 0 5700 11400
node 1156 0 9000 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 364 0.0 -0.0 1.0
element elasticBeamColumn 364 1155 1156 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 364

# zero_length_elements zeroLength
element zeroLength 1744 1154 1155 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1745 1156 32 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 90), with Mesh Node = 91 (auxiliary for element 365)
node 1157 3800 14500 4800
rigidLink beam 268 1157


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 180), with Mesh Node = 181 (auxiliary for element 365)
node 1158 200 14500 4800
rigidLink beam 347 1158

# Extra nodes for zeroLength
# node tag x y z
node 1159 3800 14500 4800
node 1160 200 14500 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 365 0.0 0.0 1.0
element elasticBeamColumn 365 1159 1160 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 365

# zero_length_elements zeroLength
element zeroLength 1746 1157 1159 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient -1.0 0.0 0.0 0.0 -1.0 0.0
element zeroLength 1747 1160 1158 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient -1.0 0.0 0.0 0.0 -1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 76), with Mesh Node = 77 (auxiliary for element 366)
node 1161 8000 14300 4800
rigidLink beam 254 1161

# Extra nodes for zeroLength
# node tag x y z
node 1162 8000 9000 4800
node 1163 8000 14300 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 366 0.0 -0.0 1.0
element elasticBeamColumn 366 1162 1163 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 366

# zero_length_elements zeroLength
element zeroLength 1748 31 1162 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1749 1163 1161 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 162), with Mesh Node = 163 (auxiliary for element 367)
node 1164 11800 9000 4800
rigidLink beam 329 1164

# Extra nodes for zeroLength
# node tag x y z
node 1165 8000 9000 4800
node 1166 11800 9000 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 367 0.0 0.0 1.0
element elasticBeamColumn 367 1165 1166 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 367

# zero_length_elements zeroLength
element zeroLength 1750 31 1165 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1751 1166 1164 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 167), with Mesh Node = 168 (auxiliary for element 368)
node 1167 12000 0 5000
rigidLink beam 168 1167


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 57), with Mesh Node = 58 (auxiliary for element 368)
node 1168 12000 0 7900
rigidLink beam 58 1168
# Geometric transformation command
geomTransf PDelta 368 1.0 0.0 -0.0
element forceBeamColumn 368 1167 1168 368 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 73), with Mesh Node = 74 (auxiliary for element 369)
node 1169 4200 9000 11400
rigidLink beam 251 1169

# Extra nodes for zeroLength
# node tag x y z
node 1170 4200 9000 11400
node 1171 8000 9000 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 369 0.0 0.0 1.0
element elasticBeamColumn 369 1170 1171 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 369

# zero_length_elements zeroLength
element zeroLength 1752 1169 1170 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1753 1171 33 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 174), with Mesh Node = 175 (auxiliary for element 370)
node 1172 3800 0 11400
rigidLink beam 341 1172

# Extra nodes for zeroLength
# node tag x y z
node 1173 0 0 11400
node 1174 3800 0 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 370 0.0 0.0 1.0
element elasticBeamColumn 370 1173 1174 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 370

# zero_length_elements zeroLength
element zeroLength 1754 16 1173 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1755 1174 1172 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 89), with Mesh Node = 90 (auxiliary for element 371)
node 1175 4200 14500 11400
rigidLink beam 267 1175


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 159), with Mesh Node = 160 (auxiliary for element 371)
node 1176 7800 14500 11400
rigidLink beam 326 1176

# Extra nodes for zeroLength
# node tag x y z
node 1177 4200 14500 11400
node 1178 7800 14500 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 371 0.0 0.0 1.0
element elasticBeamColumn 371 1177 1178 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 371

# zero_length_elements zeroLength
element zeroLength 1756 1175 1177 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1757 1178 1176 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 155), with Mesh Node = 156 (auxiliary for element 372)
node 1179 4000 5500 7900
rigidLink beam 156 1179
# Geometric transformation command
geomTransf PDelta 372 1.0 0.0 -0.0
element forceBeamColumn 372 2 1179 372 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 155), with Mesh Node = 156 (auxiliary for element 373)
node 1180 4000 5500 8300
rigidLink beam 156 1180
# Geometric transformation command
geomTransf PDelta 373 1.0 0.0 -0.0
element forceBeamColumn 373 1180 4 373 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 71), with Mesh Node = 72 (auxiliary for element 374)
node 1181 4000 0 5000
rigidLink beam 72 1181


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 181), with Mesh Node = 182 (auxiliary for element 374)
node 1182 4000 0 7900
rigidLink beam 182 1182
# Geometric transformation command
geomTransf PDelta 374 1.0 0.0 -0.0
element forceBeamColumn 374 1181 1182 374 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 70), with Mesh Node = 71 (auxiliary for element 375)
node 1183 8000 0 5000
rigidLink beam 71 1183


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 58), with Mesh Node = 59 (auxiliary for element 375)
node 1184 8000 0 7900
rigidLink beam 59 1184
# Geometric transformation command
geomTransf PDelta 375 1.0 0.0 -0.0
element forceBeamColumn 375 1183 1184 375 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 174), with Mesh Node = 175 (auxiliary for element 376)
node 1185 4000 0 11600
rigidLink beam 175 1185


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 83), with Mesh Node = 84 (auxiliary for element 376)
node 1186 4000 0 14500
rigidLink beam 84 1186
# Geometric transformation command
geomTransf PDelta 376 1.0 0.0 -0.0
element forceBeamColumn 376 1185 1186 376 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 181), with Mesh Node = 182 (auxiliary for element 377)
node 1187 4000 0 8300
rigidLink beam 182 1187


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 174), with Mesh Node = 175 (auxiliary for element 377)
node 1188 4000 0 11200
rigidLink beam 175 1188
# Geometric transformation command
geomTransf PDelta 377 1.0 0.0 -0.0
element forceBeamColumn 377 1187 1188 377 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 170), with Mesh Node = 171 (auxiliary for element 378)
node 1189 16000 0 5000
rigidLink beam 171 1189


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 59), with Mesh Node = 60 (auxiliary for element 378)
node 1190 16000 0 7900
rigidLink beam 60 1190
# Geometric transformation command
geomTransf PDelta 378 1.0 0.0 -0.0
element forceBeamColumn 378 1189 1190 378 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 58), with Mesh Node = 59 (auxiliary for element 379)
node 1191 8200 0 8100
rigidLink beam 236 1191


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 57), with Mesh Node = 58 (auxiliary for element 379)
node 1192 11800 0 8100
rigidLink beam 235 1192

# Extra nodes for zeroLength
# node tag x y z
node 1193 8200 0 8100
node 1194 11800 0 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 379 0.0 0.0 1.0
element elasticBeamColumn 379 1193 1194 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 379

# zero_length_elements zeroLength
element zeroLength 1758 1191 1193 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1759 1194 1192 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 181), with Mesh Node = 182 (auxiliary for element 380)
node 1195 4000 200 8100
rigidLink beam 348 1195


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 155), with Mesh Node = 156 (auxiliary for element 380)
node 1196 4000 5300 8100
rigidLink beam 322 1196

# Extra nodes for zeroLength
# node tag x y z
node 1197 4000 200 8100
node 1198 4000 5300 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 380 0.0 -0.0 1.0
element elasticBeamColumn 380 1197 1198 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 380

# zero_length_elements zeroLength
element zeroLength 1760 1195 1197 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1761 1198 1196 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 181), with Mesh Node = 182 (auxiliary for element 381)
node 1199 4200 0 8100
rigidLink beam 348 1199


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 58), with Mesh Node = 59 (auxiliary for element 381)
node 1200 7800 0 8100
rigidLink beam 236 1200

# Extra nodes for zeroLength
# node tag x y z
node 1201 4200 0 8100
node 1202 7800 0 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 381 0.0 0.0 1.0
element elasticBeamColumn 381 1201 1202 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 381

# zero_length_elements zeroLength
element zeroLength 1762 1199 1201 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1763 1202 1200 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 172), with Mesh Node = 173 (auxiliary for element 382)
node 1203 8000 14500 14900
rigidLink beam 173 1203


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 84), with Mesh Node = 85 (auxiliary for element 382)
node 1204 8000 14500 17800
rigidLink beam 85 1204
# Geometric transformation command
geomTransf PDelta 382 1.0 0.0 -0.0
element forceBeamColumn 382 1203 1204 382 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 78), with Mesh Node = 79 (auxiliary for element 383)
node 1205 4000 5500 14500
rigidLink beam 79 1205
# Geometric transformation command
geomTransf PDelta 383 1.0 0.0 -0.0
element forceBeamColumn 383 4 1205 383 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 75), with Mesh Node = 76 (auxiliary for element 384)
node 1206 3800 14500 14700
rigidLink beam 253 1206


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 77), with Mesh Node = 78 (auxiliary for element 384)
node 1207 200 14500 14700
rigidLink beam 255 1207

# Extra nodes for zeroLength
# node tag x y z
node 1208 3800 14500 14700
node 1209 200 14500 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 384 0.0 0.0 1.0
element elasticBeamColumn 384 1208 1209 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 384

# zero_length_elements zeroLength
element zeroLength 1764 1206 1208 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient -1.0 0.0 0.0 0.0 -1.0 0.0
element zeroLength 1765 1209 1207 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient -1.0 0.0 0.0 0.0 -1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 78), with Mesh Node = 79 (auxiliary for element 385)
node 1210 4000 5500 14900
rigidLink beam 79 1210
# Geometric transformation command
geomTransf PDelta 385 1.0 0.0 -0.0
element forceBeamColumn 385 1210 12 385 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 161), with Mesh Node = 162 (auxiliary for element 386)
node 1211 8000 0 11600
rigidLink beam 162 1211


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 182), with Mesh Node = 183 (auxiliary for element 386)
node 1212 8000 0 14500
rigidLink beam 183 1212
# Geometric transformation command
geomTransf PDelta 386 1.0 0.0 -0.0
element forceBeamColumn 386 1211 1212 386 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 62), with Mesh Node = 63 (auxiliary for element 387)
node 1213 12000 9000 11600
rigidLink beam 63 1213
# Geometric transformation command
geomTransf PDelta 387 1.0 0.0 -0.0
element forceBeamColumn 387 1213 37 387 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 69), with Mesh Node = 70 (auxiliary for element 388)
node 1214 8000 5500 11600
rigidLink beam 70 1214
# Geometric transformation command
geomTransf PDelta 388 1.0 0.0 -0.0
element forceBeamColumn 388 1214 8 388 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 183), with Mesh Node = 184 (auxiliary for element 389)
node 1215 20000 5500 14500
rigidLink beam 184 1215
# Geometric transformation command
geomTransf PDelta 389 1.0 0.0 -0.0
element forceBeamColumn 389 10 1215 389 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 158), with Mesh Node = 159 (auxiliary for element 390)
node 1216 12000 14500 14900
rigidLink beam 159 1216


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 85), with Mesh Node = 86 (auxiliary for element 390)
node 1217 12000 14500 17800
rigidLink beam 86 1217
# Geometric transformation command
geomTransf PDelta 390 1.0 0.0 -0.0
element forceBeamColumn 390 1216 1217 390 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 184), with Mesh Node = 185 (auxiliary for element 391)
node 1218 20000 9000 17800
rigidLink beam 185 1218
# Geometric transformation command
geomTransf PDelta 391 1.0 0.0 -0.0
element forceBeamColumn 391 25 1218 391 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 82), with Mesh Node = 83 (auxiliary for element 392)
node 1219 8000 5500 17800
rigidLink beam 83 1219
# Geometric transformation command
geomTransf PDelta 392 1.0 0.0 -0.0
element forceBeamColumn 392 8 1219 392 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 185), with Mesh Node = 186 (auxiliary for element 393)
node 1220 12000 200 14700
rigidLink beam 352 1220


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 164), with Mesh Node = 165 (auxiliary for element 393)
node 1221 12000 5300 14700
rigidLink beam 331 1221

# Extra nodes for zeroLength
# node tag x y z
node 1222 12000 200 14700
node 1223 12000 5300 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 393 0.0 -0.0 1.0
element elasticBeamColumn 393 1222 1223 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 393

# zero_length_elements zeroLength
element zeroLength 1766 1220 1222 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1767 1223 1221 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 177), with Mesh Node = 178 (auxiliary for element 394)
node 1224 12000 9000 17800
rigidLink beam 178 1224
# Geometric transformation command
geomTransf PDelta 394 1.0 0.0 -0.0
element forceBeamColumn 394 37 1224 394 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 66), with Mesh Node = 67 (auxiliary for element 395)
node 1225 20000 14500 11600
rigidLink beam 67 1225


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 176), with Mesh Node = 177 (auxiliary for element 395)
node 1226 20000 14500 14500
rigidLink beam 177 1226
# Geometric transformation command
geomTransf PDelta 395 1.0 0.0 -0.0
element forceBeamColumn 395 1225 1226 395 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 175), with Mesh Node = 176 (auxiliary for element 396)
node 1227 20000 14500 5000
rigidLink beam 176 1227


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 154), with Mesh Node = 155 (auxiliary for element 396)
node 1228 20000 14500 7900
rigidLink beam 155 1228
# Geometric transformation command
geomTransf PDelta 396 1.0 0.0 -0.0
element forceBeamColumn 396 1227 1228 396 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 185), with Mesh Node = 186 (auxiliary for element 397)
node 1229 12200 0 14700
rigidLink beam 352 1229


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 186), with Mesh Node = 187 (auxiliary for element 397)
node 1230 15800 0 14700
rigidLink beam 353 1230

# Extra nodes for zeroLength
# node tag x y z
node 1231 12200 0 14700
node 1232 15800 0 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 397 0.0 0.0 1.0
element elasticBeamColumn 397 1231 1232 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 397

# zero_length_elements zeroLength
element zeroLength 1768 1229 1231 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1769 1232 1230 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 176), with Mesh Node = 177 (auxiliary for element 398)
node 1233 20000 14500 14900
rigidLink beam 177 1233


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 125), with Mesh Node = 126 (auxiliary for element 398)
node 1234 20000 14500 17800
rigidLink beam 126 1234
# Geometric transformation command
geomTransf PDelta 398 1.0 0.0 -0.0
element forceBeamColumn 398 1233 1234 398 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 187), with Mesh Node = 188 (auxiliary for element 399)
node 1235 19800 0 14700
rigidLink beam 354 1235


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 186), with Mesh Node = 187 (auxiliary for element 399)
node 1236 16200 0 14700
rigidLink beam 353 1236

# Extra nodes for zeroLength
# node tag x y z
node 1237 19800 0 14700
node 1238 16200 0 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 399 0.0 0.0 1.0
element elasticBeamColumn 399 1237 1238 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 399

# zero_length_elements zeroLength
element zeroLength 1770 1235 1237 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient -1.0 0.0 0.0 0.0 -1.0 0.0
element zeroLength 1771 1238 1236 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient -1.0 0.0 0.0 0.0 -1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 154), with Mesh Node = 155 (auxiliary for element 400)
node 1239 20000 14500 8300
rigidLink beam 155 1239


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 66), with Mesh Node = 67 (auxiliary for element 400)
node 1240 20000 14500 11200
rigidLink beam 67 1240
# Geometric transformation command
geomTransf PDelta 400 1.0 0.0 -0.0
element forceBeamColumn 400 1239 1240 400 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 186), with Mesh Node = 187 (auxiliary for element 401)
node 1241 16000 200 14700
rigidLink beam 353 1241

# Extra nodes for zeroLength
# node tag x y z
node 1242 16000 200 14700
node 1243 16000 5500 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 401 0.0 -0.0 1.0
element elasticBeamColumn 401 1242 1243 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 401

# zero_length_elements zeroLength
element zeroLength 1772 1241 1242 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1773 1243 9 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 188), with Mesh Node = 189 (auxiliary for element 402)
node 1244 16000 5500 17800
rigidLink beam 189 1244
# Geometric transformation command
geomTransf PDelta 402 1.0 0.0 -0.0
element forceBeamColumn 402 9 1244 402 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 160), with Mesh Node = 161 (auxiliary for element 403)
node 1245 12000 0 11600
rigidLink beam 161 1245


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 185), with Mesh Node = 186 (auxiliary for element 403)
node 1246 12000 0 14500
rigidLink beam 186 1246
# Geometric transformation command
geomTransf PDelta 403 1.0 0.0 -0.0
element forceBeamColumn 403 1245 1246 403 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 185), with Mesh Node = 186 (auxiliary for element 404)
node 1247 12000 0 14900
rigidLink beam 186 1247


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 189), with Mesh Node = 190 (auxiliary for element 404)
node 1248 12000 0 17800
rigidLink beam 190 1248
# Geometric transformation command
geomTransf PDelta 404 1.0 0.0 -0.0
element forceBeamColumn 404 1247 1248 404 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 182), with Mesh Node = 183 (auxiliary for element 405)
node 1249 8200 0 14700
rigidLink beam 349 1249


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 185), with Mesh Node = 186 (auxiliary for element 405)
node 1250 11800 0 14700
rigidLink beam 352 1250

# Extra nodes for zeroLength
# node tag x y z
node 1251 8200 0 14700
node 1252 11800 0 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 405 0.0 0.0 1.0
element elasticBeamColumn 405 1251 1252 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 405

# zero_length_elements zeroLength
element zeroLength 1774 1249 1251 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1775 1252 1250 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 157), with Mesh Node = 158 (auxiliary for element 406)
node 1253 16000 0 11600
rigidLink beam 158 1253


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 186), with Mesh Node = 187 (auxiliary for element 406)
node 1254 16000 0 14500
rigidLink beam 187 1254
# Geometric transformation command
geomTransf PDelta 406 1.0 0.0 -0.0
element forceBeamColumn 406 1253 1254 406 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 190), with Mesh Node = 191 (auxiliary for element 407)
node 1255 8200 0 18000
rigidLink beam 357 1255


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 189), with Mesh Node = 190 (auxiliary for element 407)
node 1256 11800 0 18000
rigidLink beam 356 1256

# Extra nodes for zeroLength
# node tag x y z
node 1257 8200 0 18000
node 1258 11800 0 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 407 0.0 0.0 1.0
element elasticBeamColumn 407 1257 1258 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 407

# zero_length_elements zeroLength
element zeroLength 1776 1255 1257 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1777 1258 1256 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 85), with Mesh Node = 86 (auxiliary for element 408)
node 1259 12200 14500 18000
rigidLink beam 263 1259


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 191), with Mesh Node = 192 (auxiliary for element 408)
node 1260 15800 14500 18000
rigidLink beam 358 1260

# Extra nodes for zeroLength
# node tag x y z
node 1261 12200 14500 18000
node 1262 15800 14500 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 408 0.0 0.0 1.0
element elasticBeamColumn 408 1261 1262 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 408

# zero_length_elements zeroLength
element zeroLength 1778 1259 1261 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1779 1262 1260 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 173), with Mesh Node = 174 (auxiliary for element 409)
node 1263 16200 14500 4800
rigidLink beam 340 1263


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 175), with Mesh Node = 176 (auxiliary for element 409)
node 1264 19800 14500 4800
rigidLink beam 342 1264

# Extra nodes for zeroLength
# node tag x y z
node 1265 16200 14500 4800
node 1266 19800 14500 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 409 0.0 0.0 1.0
element elasticBeamColumn 409 1265 1266 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 409

# zero_length_elements zeroLength
element zeroLength 1780 1263 1265 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1781 1266 1264 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 186), with Mesh Node = 187 (auxiliary for element 410)
node 1267 16000 0 14900
rigidLink beam 187 1267


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 192), with Mesh Node = 193 (auxiliary for element 410)
node 1268 16000 0 17800
rigidLink beam 193 1268
# Geometric transformation command
geomTransf PDelta 410 1.0 0.0 -0.0
element forceBeamColumn 410 1267 1268 410 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 158), with Mesh Node = 159 (auxiliary for element 411)
node 1269 12000 14300 14700
rigidLink beam 325 1269

# Extra nodes for zeroLength
# node tag x y z
node 1270 12000 9000 14700
node 1271 12000 14300 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 411 0.0 -0.0 1.0
element elasticBeamColumn 411 1270 1271 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 411

# zero_length_elements zeroLength
element zeroLength 1782 37 1270 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1783 1271 1269 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 182), with Mesh Node = 183 (auxiliary for element 412)
node 1272 8000 200 14700
rigidLink beam 349 1272

# Extra nodes for zeroLength
# node tag x y z
node 1273 8000 200 14700
node 1274 8000 5500 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 412 0.0 -0.0 1.0
element elasticBeamColumn 412 1273 1274 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 412

# zero_length_elements zeroLength
element zeroLength 1784 1272 1273 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1785 1274 8 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 166), with Mesh Node = 167 (auxiliary for element 413)
node 1275 12000 14500 4600
rigidLink beam 167 1275
# Geometric transformation command
geomTransf PDelta 413 1.0 0.0 -0.0
element forceBeamColumn 413 194 1275 413 HingeRadau 6 200.0 6 200.0 7


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 176), with Mesh Node = 177 (auxiliary for element 414)
node 1276 20000 14300 14700
rigidLink beam 343 1276

# Extra nodes for zeroLength
# node tag x y z
node 1277 20000 9000 14700
node 1278 20000 14300 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 414 0.0 -0.0 1.0
element elasticBeamColumn 414 1277 1278 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 414

# zero_length_elements zeroLength
element zeroLength 1786 25 1277 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1787 1278 1276 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 152), with Mesh Node = 153 (auxiliary for element 415)
node 1279 16000 14500 8300
rigidLink beam 153 1279


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 65), with Mesh Node = 66 (auxiliary for element 415)
node 1280 16000 14500 11200
rigidLink beam 66 1280
# Geometric transformation command
geomTransf PDelta 415 1.0 0.0 -0.0
element forceBeamColumn 415 1279 1280 415 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 188), with Mesh Node = 189 (auxiliary for element 416)
node 1281 16000 5700 18000
rigidLink beam 355 1281

# Extra nodes for zeroLength
# node tag x y z
node 1282 16000 5700 18000
node 1283 16000 9000 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 416 0.0 -0.0 1.0
element elasticBeamColumn 416 1282 1283 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 416

# zero_length_elements zeroLength
element zeroLength 1788 1281 1282 -mat 5 5 5 5 55 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1789 1283 40 -mat 5 5 5 5 55 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 188), with Mesh Node = 189 (auxiliary for element 417)
node 1284 15800 5500 18000
rigidLink beam 355 1284

# Extra nodes for zeroLength
# node tag x y z
node 1285 12000 5500 18000
node 1286 15800 5500 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 417 0.0 0.0 1.0
element elasticBeamColumn 417 1285 1286 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 417

# zero_length_elements zeroLength
element zeroLength 1790 13 1285 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1791 1286 1284 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 191), with Mesh Node = 192 (auxiliary for element 418)
node 1287 16200 14500 18000
rigidLink beam 358 1287


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 125), with Mesh Node = 126 (auxiliary for element 418)
node 1288 19800 14500 18000
rigidLink beam 303 1288

# Extra nodes for zeroLength
# node tag x y z
node 1289 16200 14500 18000
node 1290 19800 14500 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 418 0.0 0.0 1.0
element elasticBeamColumn 418 1289 1290 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 418

# zero_length_elements zeroLength
element zeroLength 1792 1287 1289 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1793 1290 1288 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 191), with Mesh Node = 192 (auxiliary for element 419)
node 1291 16000 14300 18000
rigidLink beam 358 1291

# Extra nodes for zeroLength
# node tag x y z
node 1292 16000 9000 18000
node 1293 16000 14300 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 419 0.0 -0.0 1.0
element elasticBeamColumn 419 1292 1293 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 419

# zero_length_elements zeroLength
element zeroLength 1794 40 1292 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1795 1293 1291 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 177), with Mesh Node = 178 (auxiliary for element 420)
node 1294 12000 8800 18000
rigidLink beam 344 1294

# Extra nodes for zeroLength
# node tag x y z
node 1295 12000 5500 18000
node 1296 12000 8800 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 420 0.0 -0.0 1.0
element elasticBeamColumn 420 1295 1296 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 420

# zero_length_elements zeroLength
element zeroLength 1796 13 1295 -mat 5 5 5 5 55 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1797 1296 1294 -mat 5 5 5 5 55 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 184), with Mesh Node = 185 (auxiliary for element 421)
node 1297 20000 9200 18000
rigidLink beam 351 1297


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 125), with Mesh Node = 126 (auxiliary for element 421)
node 1298 20000 14300 18000
rigidLink beam 303 1298

# Extra nodes for zeroLength
# node tag x y z
node 1299 20000 9200 18000
node 1300 20000 14300 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 421 0.0 -0.0 1.0
element elasticBeamColumn 421 1299 1300 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 421

# zero_length_elements zeroLength
element zeroLength 1798 1297 1299 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1799 1300 1298 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 184), with Mesh Node = 185 (auxiliary for element 422)
node 1301 20000 8800 18000
rigidLink beam 351 1301

# Extra nodes for zeroLength
# node tag x y z
node 1302 20000 5500 18000
node 1303 20000 8800 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 422 0.0 -0.0 1.0
element elasticBeamColumn 422 1302 1303 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 422

# zero_length_elements zeroLength
element zeroLength 1800 15 1302 -mat 5 5 5 5 55 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1801 1303 1301 -mat 5 5 5 5 55 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 153), with Mesh Node = 154 (auxiliary for element 423)
node 1304 12000 14300 8100
rigidLink beam 320 1304

# Extra nodes for zeroLength
# node tag x y z
node 1305 12000 9000 8100
node 1306 12000 14300 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 423 0.0 -0.0 1.0
element elasticBeamColumn 423 1305 1306 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 423

# zero_length_elements zeroLength
element zeroLength 1802 35 1305 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1803 1306 1304 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 166), with Mesh Node = 167 (auxiliary for element 424)
node 1307 12000 14500 5000
rigidLink beam 167 1307


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 153), with Mesh Node = 154 (auxiliary for element 424)
node 1308 12000 14500 7900
rigidLink beam 154 1308
# Geometric transformation command
geomTransf PDelta 424 1.0 0.0 -0.0
element forceBeamColumn 424 1307 1308 424 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 194), with Mesh Node = 195 (auxiliary for element 425)
node 1309 20000 200 18000
rigidLink beam 360 1309

# Extra nodes for zeroLength
# node tag x y z
node 1310 20000 200 18000
node 1311 20000 5500 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 425 0.0 -0.0 1.0
element elasticBeamColumn 425 1310 1311 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 425

# zero_length_elements zeroLength
element zeroLength 1804 1309 1310 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1805 1311 15 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 188), with Mesh Node = 189 (auxiliary for element 426)
node 1312 16200 5500 18000
rigidLink beam 355 1312

# Extra nodes for zeroLength
# node tag x y z
node 1313 16200 5500 18000
node 1314 20000 5500 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 426 0.0 0.0 1.0
element elasticBeamColumn 426 1313 1314 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 426

# zero_length_elements zeroLength
element zeroLength 1806 1312 1313 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1807 1314 15 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 187), with Mesh Node = 188 (auxiliary for element 427)
node 1315 20000 200 14700
rigidLink beam 354 1315


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 183), with Mesh Node = 184 (auxiliary for element 427)
node 1316 20000 5300 14700
rigidLink beam 350 1316

# Extra nodes for zeroLength
# node tag x y z
node 1317 20000 200 14700
node 1318 20000 5300 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 427 0.0 -0.0 1.0
element elasticBeamColumn 427 1317 1318 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 427

# zero_length_elements zeroLength
element zeroLength 1808 1315 1317 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1809 1318 1316 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 164), with Mesh Node = 165 (auxiliary for element 428)
node 1319 12200 5500 14700
rigidLink beam 331 1319

# Extra nodes for zeroLength
# node tag x y z
node 1320 12200 5500 14700
node 1321 16000 5500 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 428 0.0 0.0 1.0
element elasticBeamColumn 428 1320 1321 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 428

# zero_length_elements zeroLength
element zeroLength 1810 1319 1320 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1811 1321 9 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 67), with Mesh Node = 68 (auxiliary for element 429)
node 1322 16000 14500 14900
rigidLink beam 68 1322


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 191), with Mesh Node = 192 (auxiliary for element 429)
node 1323 16000 14500 17800
rigidLink beam 192 1323
# Geometric transformation command
geomTransf PDelta 429 1.0 0.0 -0.0
element forceBeamColumn 429 1322 1323 429 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 178), with Mesh Node = 179 (auxiliary for element 430)
node 1324 0 14500 8300
rigidLink beam 179 1324


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 87), with Mesh Node = 88 (auxiliary for element 430)
node 1325 0 14500 11200
rigidLink beam 88 1325
# Geometric transformation command
geomTransf PDelta 430 1.0 0.0 -0.0
element forceBeamColumn 430 1324 1325 430 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 180), with Mesh Node = 181 (auxiliary for element 431)
node 1326 0 14500 5000
rigidLink beam 181 1326


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 178), with Mesh Node = 179 (auxiliary for element 431)
node 1327 0 14500 7900
rigidLink beam 179 1327
# Geometric transformation command
geomTransf PDelta 431 1.0 0.0 -0.0
element forceBeamColumn 431 1326 1327 431 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 153), with Mesh Node = 154 (auxiliary for element 432)
node 1328 12000 14500 8300
rigidLink beam 154 1328


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 68), with Mesh Node = 69 (auxiliary for element 432)
node 1329 12000 14500 11200
rigidLink beam 69 1329
# Geometric transformation command
geomTransf PDelta 432 1.0 0.0 -0.0
element forceBeamColumn 432 1328 1329 432 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 72), with Mesh Node = 73 (auxiliary for element 433)
node 1330 0 5500 5000
rigidLink beam 73 1330
# Geometric transformation command
geomTransf PDelta 433 1.0 0.0 -0.0
element forceBeamColumn 433 1330 5 433 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 155), with Mesh Node = 156 (auxiliary for element 434)
node 1331 3800 5500 8100
rigidLink beam 322 1331

# Extra nodes for zeroLength
# node tag x y z
node 1332 0 5500 8100
node 1333 3800 5500 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 434 0.0 0.0 1.0
element elasticBeamColumn 434 1332 1333 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 434

# zero_length_elements zeroLength
element zeroLength 1812 5 1332 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1813 1333 1331 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 156), with Mesh Node = 157 (auxiliary for element 435)
node 1334 0 9000 7900
rigidLink beam 157 1334
# Geometric transformation command
geomTransf PDelta 435 1.0 0.0 -0.0
element forceBeamColumn 435 34 1334 435 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 156), with Mesh Node = 157 (auxiliary for element 436)
node 1335 0 9200 8100
rigidLink beam 323 1335


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 178), with Mesh Node = 179 (auxiliary for element 436)
node 1336 0 14300 8100
rigidLink beam 345 1336

# Extra nodes for zeroLength
# node tag x y z
node 1337 0 9200 8100
node 1338 0 14300 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 436 0.0 -0.0 1.0
element elasticBeamColumn 436 1337 1338 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 436

# zero_length_elements zeroLength
element zeroLength 1814 1335 1337 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1815 1338 1336 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 53), with Mesh Node = 54 (auxiliary for element 437)
node 1339 16200 5500 4800
rigidLink beam 231 1339

# Extra nodes for zeroLength
# node tag x y z
node 1340 16200 5500 4800
node 1341 20000 5500 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 437 0.0 0.0 1.0
element elasticBeamColumn 437 1340 1341 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 437

# zero_length_elements zeroLength
element zeroLength 1816 1339 1340 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1817 1341 28 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 195), with Mesh Node = 196 (auxiliary for element 438)
node 1342 20000 200 4800
rigidLink beam 361 1342

# Extra nodes for zeroLength
# node tag x y z
node 1343 20000 5500 4800
node 1344 20000 200 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 438 0.0 0.0 1.0
element elasticBeamColumn 438 1343 1344 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 438

# zero_length_elements zeroLength
element zeroLength 1818 28 1343 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 -1.0 0.0 1.0 0.0 -0.0
element zeroLength 1819 1344 1342 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 -1.0 0.0 1.0 0.0 -0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 195), with Mesh Node = 196 (auxiliary for element 439)
node 1345 20000 0 5000
rigidLink beam 196 1345


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 196), with Mesh Node = 197 (auxiliary for element 439)
node 1346 20000 0 7900
rigidLink beam 197 1346
# Geometric transformation command
geomTransf PDelta 439 1.0 0.0 -0.0
element forceBeamColumn 439 1345 1346 439 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 196), with Mesh Node = 197 (auxiliary for element 440)
node 1347 20000 200 8100
rigidLink beam 362 1347


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 54), with Mesh Node = 55 (auxiliary for element 440)
node 1348 20000 5300 8100
rigidLink beam 232 1348

# Extra nodes for zeroLength
# node tag x y z
node 1349 20000 200 8100
node 1350 20000 5300 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 440 0.0 -0.0 1.0
element elasticBeamColumn 440 1349 1350 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 440

# zero_length_elements zeroLength
element zeroLength 1820 1347 1349 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1821 1350 1348 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 54), with Mesh Node = 55 (auxiliary for element 441)
node 1351 20000 5500 7900
rigidLink beam 55 1351
# Geometric transformation command
geomTransf PDelta 441 1.0 0.0 -0.0
element forceBeamColumn 441 28 1351 441 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 57), with Mesh Node = 58 (auxiliary for element 442)
node 1352 12200 0 8100
rigidLink beam 235 1352


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 59), with Mesh Node = 60 (auxiliary for element 442)
node 1353 15800 0 8100
rigidLink beam 237 1353

# Extra nodes for zeroLength
# node tag x y z
node 1354 12200 0 8100
node 1355 15800 0 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 442 0.0 0.0 1.0
element elasticBeamColumn 442 1354 1355 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 442

# zero_length_elements zeroLength
element zeroLength 1822 1352 1354 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1823 1355 1353 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 59), with Mesh Node = 60 (auxiliary for element 443)
node 1356 16200 0 8100
rigidLink beam 237 1356


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 196), with Mesh Node = 197 (auxiliary for element 443)
node 1357 19800 0 8100
rigidLink beam 362 1357

# Extra nodes for zeroLength
# node tag x y z
node 1358 16200 0 8100
node 1359 19800 0 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 443 0.0 0.0 1.0
element elasticBeamColumn 443 1358 1359 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 443

# zero_length_elements zeroLength
element zeroLength 1824 1356 1358 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1825 1359 1357 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 61), with Mesh Node = 62 (auxiliary for element 444)
node 1360 16000 9000 14900
rigidLink beam 62 1360
# Geometric transformation command
geomTransf PDelta 444 1.0 0.0 -0.0
element forceBeamColumn 444 1360 40 444 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 64), with Mesh Node = 65 (auxiliary for element 445)
node 1361 20000 9000 11600
rigidLink beam 65 1361
# Geometric transformation command
geomTransf PDelta 445 1.0 0.0 -0.0
element forceBeamColumn 445 1361 25 445 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 183), with Mesh Node = 184 (auxiliary for element 446)
node 1362 20000 5700 14700
rigidLink beam 350 1362

# Extra nodes for zeroLength
# node tag x y z
node 1363 20000 5700 14700
node 1364 20000 9000 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 446 0.0 -0.0 1.0
element elasticBeamColumn 446 1363 1364 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 446

# zero_length_elements zeroLength
element zeroLength 1826 1362 1363 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1827 1364 25 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 183), with Mesh Node = 184 (auxiliary for element 447)
node 1365 19800 5500 14700
rigidLink beam 350 1365

# Extra nodes for zeroLength
# node tag x y z
node 1366 16000 5500 14700
node 1367 19800 5500 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 447 0.0 0.0 1.0
element elasticBeamColumn 447 1366 1367 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 447

# zero_length_elements zeroLength
element zeroLength 1828 9 1366 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1829 1367 1365 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 190), with Mesh Node = 191 (auxiliary for element 448)
node 1368 8000 200 18000
rigidLink beam 357 1368


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 82), with Mesh Node = 83 (auxiliary for element 448)
node 1369 8000 5300 18000
rigidLink beam 260 1369

# Extra nodes for zeroLength
# node tag x y z
node 1370 8000 200 18000
node 1371 8000 5300 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 448 0.0 -0.0 1.0
element elasticBeamColumn 448 1370 1371 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 448

# zero_length_elements zeroLength
element zeroLength 1830 1368 1370 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1831 1371 1369 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 177), with Mesh Node = 178 (auxiliary for element 449)
node 1372 12000 9200 18000
rigidLink beam 344 1372


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 85), with Mesh Node = 86 (auxiliary for element 449)
node 1373 12000 14300 18000
rigidLink beam 263 1373

# Extra nodes for zeroLength
# node tag x y z
node 1374 12000 9200 18000
node 1375 12000 14300 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 449 0.0 -0.0 1.0
element elasticBeamColumn 449 1374 1375 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 449

# zero_length_elements zeroLength
element zeroLength 1832 1372 1374 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1833 1375 1373 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 82), with Mesh Node = 83 (auxiliary for element 450)
node 1376 8200 5500 18000
rigidLink beam 260 1376

# Extra nodes for zeroLength
# node tag x y z
node 1377 8200 5500 18000
node 1378 12000 5500 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 450 0.0 0.0 1.0
element elasticBeamColumn 450 1377 1378 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 450

# zero_length_elements zeroLength
element zeroLength 1834 1376 1377 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1835 1378 13 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 69), with Mesh Node = 70 (auxiliary for element 451)
node 1379 7800 5500 11400
rigidLink beam 247 1379

# Extra nodes for zeroLength
# node tag x y z
node 1380 4000 5500 11400
node 1381 7800 5500 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 451 0.0 0.0 1.0
element elasticBeamColumn 451 1380 1381 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 451

# zero_length_elements zeroLength
element zeroLength 1836 4 1380 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1837 1381 1379 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 182), with Mesh Node = 183 (auxiliary for element 452)
node 1382 8000 0 14900
rigidLink beam 183 1382


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 190), with Mesh Node = 191 (auxiliary for element 452)
node 1383 8000 0 17800
rigidLink beam 191 1383
# Geometric transformation command
geomTransf PDelta 452 1.0 0.0 -0.0
element forceBeamColumn 452 1382 1383 452 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 73), with Mesh Node = 74 (auxiliary for element 453)
node 1384 4000 8800 11400
rigidLink beam 251 1384

# Extra nodes for zeroLength
# node tag x y z
node 1385 4000 5500 11400
node 1386 4000 8800 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 453 0.0 -0.0 1.0
element elasticBeamColumn 453 1385 1386 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 453

# zero_length_elements zeroLength
element zeroLength 1838 4 1385 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1839 1386 1384 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 88), with Mesh Node = 89 (auxiliary for element 454)
node 1387 200 5500 11400
rigidLink beam 266 1387

# Extra nodes for zeroLength
# node tag x y z
node 1388 200 5500 11400
node 1389 4000 5500 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 454 0.0 0.0 1.0
element elasticBeamColumn 454 1388 1389 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 454

# zero_length_elements zeroLength
element zeroLength 1840 1387 1388 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1841 1389 4 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 90), with Mesh Node = 91 (auxiliary for element 455)
node 1390 4200 14500 4800
rigidLink beam 268 1390


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 76), with Mesh Node = 77 (auxiliary for element 455)
node 1391 7800 14500 4800
rigidLink beam 254 1391

# Extra nodes for zeroLength
# node tag x y z
node 1392 4200 14500 4800
node 1393 7800 14500 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 455 0.0 0.0 1.0
element elasticBeamColumn 455 1392 1393 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 455

# zero_length_elements zeroLength
element zeroLength 1842 1390 1392 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1843 1393 1391 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 88), with Mesh Node = 89 (auxiliary for element 456)
node 1394 0 5300 11400
rigidLink beam 266 1394

# Extra nodes for zeroLength
# node tag x y z
node 1395 0 0 11400
node 1396 0 5300 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 456 0.0 -0.0 1.0
element elasticBeamColumn 456 1395 1396 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 456

# zero_length_elements zeroLength
element zeroLength 1844 16 1395 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1845 1396 1394 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 89), with Mesh Node = 90 (auxiliary for element 457)
node 1397 4000 14500 11600
rigidLink beam 90 1397


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 75), with Mesh Node = 76 (auxiliary for element 457)
node 1398 4000 14500 14500
rigidLink beam 76 1398
# Geometric transformation command
geomTransf PDelta 457 1.0 0.0 -0.0
element forceBeamColumn 457 1397 1398 457 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 90), with Mesh Node = 91 (auxiliary for element 458)
node 1399 4000 14500 5000
rigidLink beam 91 1399


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 171), with Mesh Node = 172 (auxiliary for element 458)
node 1400 4000 14500 7900
rigidLink beam 172 1400
# Geometric transformation command
geomTransf PDelta 458 1.0 0.0 -0.0
element forceBeamColumn 458 1399 1400 458 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 75), with Mesh Node = 76 (auxiliary for element 459)
node 1401 4000 14500 14900
rigidLink beam 76 1401


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 80), with Mesh Node = 81 (auxiliary for element 459)
node 1402 4000 14500 17800
rigidLink beam 81 1402
# Geometric transformation command
geomTransf PDelta 459 1.0 0.0 -0.0
element forceBeamColumn 459 1401 1402 459 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 171), with Mesh Node = 172 (auxiliary for element 460)
node 1403 4000 14500 8300
rigidLink beam 172 1403


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 89), with Mesh Node = 90 (auxiliary for element 460)
node 1404 4000 14500 11200
rigidLink beam 90 1404
# Geometric transformation command
geomTransf PDelta 460 1.0 0.0 -0.0
element forceBeamColumn 460 1403 1404 460 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 92), with Mesh Node = 93 (auxiliary for element 461)
node 1405 200 0 14700
rigidLink beam 270 1405


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 83), with Mesh Node = 84 (auxiliary for element 461)
node 1406 3800 0 14700
rigidLink beam 261 1406

# Extra nodes for zeroLength
# node tag x y z
node 1407 200 0 14700
node 1408 3800 0 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 461 0.0 0.0 1.0
element elasticBeamColumn 461 1407 1408 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 461

# zero_length_elements zeroLength
element zeroLength 1846 1405 1407 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1847 1408 1406 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 80), with Mesh Node = 81 (auxiliary for element 462)
node 1409 4200 14500 18000
rigidLink beam 258 1409


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 84), with Mesh Node = 85 (auxiliary for element 462)
node 1410 7800 14500 18000
rigidLink beam 262 1410

# Extra nodes for zeroLength
# node tag x y z
node 1411 4200 14500 18000
node 1412 7800 14500 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 462 0.0 0.0 1.0
element elasticBeamColumn 462 1411 1412 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 462

# zero_length_elements zeroLength
element zeroLength 1848 1409 1411 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1849 1412 1410 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 80), with Mesh Node = 81 (auxiliary for element 463)
node 1413 3800 14500 18000
rigidLink beam 258 1413


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 81), with Mesh Node = 82 (auxiliary for element 463)
node 1414 200 14500 18000
rigidLink beam 259 1414

# Extra nodes for zeroLength
# node tag x y z
node 1415 3800 14500 18000
node 1416 200 14500 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 463 0.0 0.0 1.0
element elasticBeamColumn 463 1415 1416 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 463

# zero_length_elements zeroLength
element zeroLength 1850 1413 1415 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient -1.0 0.0 0.0 0.0 -1.0 0.0
element zeroLength 1851 1416 1414 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient -1.0 0.0 0.0 0.0 -1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 83), with Mesh Node = 84 (auxiliary for element 464)
node 1417 4200 0 14700
rigidLink beam 261 1417


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 182), with Mesh Node = 183 (auxiliary for element 464)
node 1418 7800 0 14700
rigidLink beam 349 1418

# Extra nodes for zeroLength
# node tag x y z
node 1419 4200 0 14700
node 1420 7800 0 14700

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 464 0.0 0.0 1.0
element elasticBeamColumn 464 1419 1420 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 464

# zero_length_elements zeroLength
element zeroLength 1852 1417 1419 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1853 1420 1418 -mat 5 5 5 5 29 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 174), with Mesh Node = 175 (auxiliary for element 465)
node 1421 4000 200 11400
rigidLink beam 341 1421

# Extra nodes for zeroLength
# node tag x y z
node 1422 4000 200 11400
node 1423 4000 5500 11400

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 465 0.0 -0.0 1.0
element elasticBeamColumn 465 1422 1423 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 465

# zero_length_elements zeroLength
element zeroLength 1854 1421 1422 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1855 1423 4 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 86), with Mesh Node = 87 (auxiliary for element 466)
node 1424 4200 0 18000
rigidLink beam 264 1424


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 190), with Mesh Node = 191 (auxiliary for element 466)
node 1425 7800 0 18000
rigidLink beam 357 1425

# Extra nodes for zeroLength
# node tag x y z
node 1426 4200 0 18000
node 1427 7800 0 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 466 0.0 0.0 1.0
element elasticBeamColumn 466 1426 1427 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 466

# zero_length_elements zeroLength
element zeroLength 1856 1424 1426 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1857 1427 1425 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 179), with Mesh Node = 180 (auxiliary for element 467)
node 1428 200 0 8100
rigidLink beam 346 1428


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 181), with Mesh Node = 182 (auxiliary for element 467)
node 1429 3800 0 8100
rigidLink beam 348 1429

# Extra nodes for zeroLength
# node tag x y z
node 1430 200 0 8100
node 1431 3800 0 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 467 0.0 0.0 1.0
element elasticBeamColumn 467 1430 1431 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 467

# zero_length_elements zeroLength
element zeroLength 1858 1428 1430 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1859 1431 1429 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 92), with Mesh Node = 93 (auxiliary for element 468)
node 1432 0 0 14500
rigidLink beam 93 1432
# Geometric transformation command
geomTransf PDelta 468 1.0 0.0 -0.0
element forceBeamColumn 468 16 1432 468 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 92), with Mesh Node = 93 (auxiliary for element 469)
node 1433 0 0 14900
rigidLink beam 93 1433


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 91), with Mesh Node = 92 (auxiliary for element 469)
node 1434 0 0 17800
rigidLink beam 92 1434
# Geometric transformation command
geomTransf PDelta 469 1.0 0.0 -0.0
element forceBeamColumn 469 1433 1434 469 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 105), with Mesh Node = 106 (auxiliary for element 470)
node 1435 16000 9000 21100
rigidLink beam 106 1435
# Geometric transformation command
geomTransf PDelta 470 1.0 0.0 -0.0
element forceBeamColumn 470 40 1435 470 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 105), with Mesh Node = 106 (auxiliary for element 471)
node 1436 16000 9000 21500
rigidLink beam 106 1436
# Geometric transformation command
geomTransf PDelta 471 1.0 0.0 -0.0
element forceBeamColumn 471 1436 44 471 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 177), with Mesh Node = 178 (auxiliary for element 472)
node 1437 12000 9000 18200
rigidLink beam 178 1437
# Geometric transformation command
geomTransf PDelta 472 1.0 0.0 -0.0
element forceBeamColumn 472 1437 41 472 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 105), with Mesh Node = 106 (auxiliary for element 473)
node 1438 16000 9200 21300
rigidLink beam 283 1438


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 97), with Mesh Node = 98 (auxiliary for element 473)
node 1439 16000 14300 21300
rigidLink beam 275 1439

# Extra nodes for zeroLength
# node tag x y z
node 1440 16000 9200 21300
node 1441 16000 14300 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 473 0.0 -0.0 1.0
element elasticBeamColumn 473 1440 1441 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 473

# zero_length_elements zeroLength
element zeroLength 1860 1438 1440 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1861 1441 1439 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 184), with Mesh Node = 185 (auxiliary for element 474)
node 1442 20000 9000 18200
rigidLink beam 185 1442
# Geometric transformation command
geomTransf PDelta 474 1.0 0.0 -0.0
element forceBeamColumn 474 1442 26 474 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 197), with Mesh Node = 198 (auxiliary for element 475)
node 1443 20000 9000 24400
rigidLink beam 198 1443
# Geometric transformation command
geomTransf PDelta 475 1.0 0.0 -0.0
element forceBeamColumn 475 26 1443 475 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 122), with Mesh Node = 123 (auxiliary for element 476)
node 1444 20000 14300 21300
rigidLink beam 300 1444

# Extra nodes for zeroLength
# node tag x y z
node 1445 20000 9000 21300
node 1446 20000 14300 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 476 0.0 -0.0 1.0
element elasticBeamColumn 476 1445 1446 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 476

# zero_length_elements zeroLength
element zeroLength 1862 26 1445 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1863 1446 1444 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 97), with Mesh Node = 98 (auxiliary for element 477)
node 1447 16000 14500 21500
rigidLink beam 98 1447


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 108), with Mesh Node = 109 (auxiliary for element 477)
node 1448 16000 14500 24400
rigidLink beam 109 1448
# Geometric transformation command
geomTransf PDelta 477 1.0 0.0 -0.0
element forceBeamColumn 477 1447 1448 477 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 95), with Mesh Node = 96 (auxiliary for element 478)
node 1449 12000 14300 21300
rigidLink beam 273 1449

# Extra nodes for zeroLength
# node tag x y z
node 1450 12000 9000 21300
node 1451 12000 14300 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 478 0.0 -0.0 1.0
element elasticBeamColumn 478 1450 1451 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 478

# zero_length_elements zeroLength
element zeroLength 1864 41 1450 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1865 1451 1449 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 197), with Mesh Node = 198 (auxiliary for element 479)
node 1452 20000 8800 24600
rigidLink beam 363 1452

# Extra nodes for zeroLength
# node tag x y z
node 1453 20000 5500 24600
node 1454 20000 8800 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 479 0.0 -0.0 1.0
element elasticBeamColumn 479 1453 1454 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 479

# zero_length_elements zeroLength
element zeroLength 1866 21 1453 -mat 5 5 5 5 53 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1867 1454 1452 -mat 5 5 5 5 53 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 103), with Mesh Node = 104 (auxiliary for element 480)
node 1455 8000 14500 24800
rigidLink beam 104 1455


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 139), with Mesh Node = 140 (auxiliary for element 480)
node 1456 8000 14500 27700
rigidLink beam 140 1456
# Geometric transformation command
geomTransf PDelta 480 1.0 0.0 -0.0
element forceBeamColumn 480 1455 1456 480 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 108), with Mesh Node = 109 (auxiliary for element 481)
node 1457 16000 14500 24800
rigidLink beam 109 1457


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 132), with Mesh Node = 133 (auxiliary for element 481)
node 1458 16000 14500 27700
rigidLink beam 133 1458
# Geometric transformation command
geomTransf PDelta 481 1.0 0.0 -0.0
element forceBeamColumn 481 1457 1458 481 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 198), with Mesh Node = 199 (auxiliary for element 482)
node 1459 20000 200 24600
rigidLink beam 364 1459

# Extra nodes for zeroLength
# node tag x y z
node 1460 20000 200 24600
node 1461 20000 5500 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 482 0.0 -0.0 1.0
element elasticBeamColumn 482 1460 1461 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 482

# zero_length_elements zeroLength
element zeroLength 1868 1459 1460 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1869 1461 21 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 199), with Mesh Node = 200 (auxiliary for element 483)
node 1462 16200 5500 24600
rigidLink beam 365 1462

# Extra nodes for zeroLength
# node tag x y z
node 1463 16200 5500 24600
node 1464 20000 5500 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 483 0.0 0.0 1.0
element elasticBeamColumn 483 1463 1464 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 483

# zero_length_elements zeroLength
element zeroLength 1870 1462 1463 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1871 1464 21 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 199), with Mesh Node = 200 (auxiliary for element 484)
node 1465 15800 5500 24600
rigidLink beam 365 1465

# Extra nodes for zeroLength
# node tag x y z
node 1466 12000 5500 24600
node 1467 15800 5500 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 484 0.0 0.0 1.0
element elasticBeamColumn 484 1466 1467 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 484

# zero_length_elements zeroLength
element zeroLength 1872 19 1466 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1873 1467 1465 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 197), with Mesh Node = 198 (auxiliary for element 485)
node 1468 20000 9200 24600
rigidLink beam 363 1468


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 109), with Mesh Node = 110 (auxiliary for element 485)
node 1469 20000 14300 24600
rigidLink beam 287 1469

# Extra nodes for zeroLength
# node tag x y z
node 1470 20000 9200 24600
node 1471 20000 14300 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 485 0.0 -0.0 1.0
element elasticBeamColumn 485 1470 1471 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 485

# zero_length_elements zeroLength
element zeroLength 1874 1468 1470 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1875 1471 1469 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 191), with Mesh Node = 192 (auxiliary for element 486)
node 1472 16000 14500 18200
rigidLink beam 192 1472


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 97), with Mesh Node = 98 (auxiliary for element 486)
node 1473 16000 14500 21100
rigidLink beam 98 1473
# Geometric transformation command
geomTransf PDelta 486 1.0 0.0 -0.0
element forceBeamColumn 486 1472 1473 486 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 200), with Mesh Node = 201 (auxiliary for element 487)
node 1474 16000 9200 27900
rigidLink beam 366 1474


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 132), with Mesh Node = 133 (auxiliary for element 487)
node 1475 16000 14300 27900
rigidLink beam 310 1475

# Extra nodes for zeroLength
# node tag x y z
node 1476 16000 9200 27900
node 1477 16000 14300 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 487 0.0 -0.0 1.0
element elasticBeamColumn 487 1476 1477 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 487

# zero_length_elements zeroLength
element zeroLength 1876 1474 1476 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1877 1477 1475 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 132), with Mesh Node = 133 (auxiliary for element 488)
node 1478 16200 14500 27900
rigidLink beam 310 1478


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 124), with Mesh Node = 125 (auxiliary for element 488)
node 1479 19800 14500 27900
rigidLink beam 302 1479

# Extra nodes for zeroLength
# node tag x y z
node 1480 16200 14500 27900
node 1481 19800 14500 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 488 0.0 0.0 1.0
element elasticBeamColumn 488 1480 1481 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 488

# zero_length_elements zeroLength
element zeroLength 1878 1478 1480 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1879 1481 1479 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 128), with Mesh Node = 129 (auxiliary for element 489)
node 1482 12200 5500 27900
rigidLink beam 306 1482

# Extra nodes for zeroLength
# node tag x y z
node 1483 12200 5500 27900
node 1484 16000 5500 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 489 0.0 0.0 1.0
element elasticBeamColumn 489 1483 1484 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 489

# zero_length_elements zeroLength
element zeroLength 1880 1482 1483 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1881 1484 24 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 128), with Mesh Node = 129 (auxiliary for element 490)
node 1485 12000 5700 27900
rigidLink beam 306 1485

# Extra nodes for zeroLength
# node tag x y z
node 1486 12000 5700 27900
node 1487 12000 9000 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 490 0.0 -0.0 1.0
element elasticBeamColumn 490 1486 1487 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 490

# zero_length_elements zeroLength
element zeroLength 1882 1485 1486 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1883 1487 45 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 124), with Mesh Node = 125 (auxiliary for element 491)
node 1488 20000 14300 27900
rigidLink beam 302 1488

# Extra nodes for zeroLength
# node tag x y z
node 1489 20000 9000 27900
node 1490 20000 14300 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 491 0.0 -0.0 1.0
element elasticBeamColumn 491 1489 1490 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 491

# zero_length_elements zeroLength
element zeroLength 1884 46 1489 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1885 1490 1488 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 201), with Mesh Node = 202 (auxiliary for element 492)
node 1491 19800 5500 27900
rigidLink beam 367 1491

# Extra nodes for zeroLength
# node tag x y z
node 1492 16000 5500 27900
node 1493 19800 5500 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 492 0.0 0.0 1.0
element elasticBeamColumn 492 1492 1493 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 492

# zero_length_elements zeroLength
element zeroLength 1886 24 1492 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1887 1493 1491 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 95), with Mesh Node = 96 (auxiliary for element 493)
node 1494 12000 14500 21500
rigidLink beam 96 1494


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 107), with Mesh Node = 108 (auxiliary for element 493)
node 1495 12000 14500 24400
rigidLink beam 108 1495
# Geometric transformation command
geomTransf PDelta 493 1.0 0.0 -0.0
element forceBeamColumn 493 1494 1495 493 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 202), with Mesh Node = 203 (auxiliary for element 494)
node 1496 20000 200 27900
rigidLink beam 368 1496


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 201), with Mesh Node = 202 (auxiliary for element 494)
node 1497 20000 5300 27900
rigidLink beam 367 1497

# Extra nodes for zeroLength
# node tag x y z
node 1498 20000 200 27900
node 1499 20000 5300 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 494 0.0 -0.0 1.0
element elasticBeamColumn 494 1498 1499 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 494

# zero_length_elements zeroLength
element zeroLength 1888 1496 1498 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1889 1499 1497 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 189), with Mesh Node = 190 (auxiliary for element 495)
node 1500 12000 0 18200
rigidLink beam 190 1500


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 99), with Mesh Node = 100 (auxiliary for element 495)
node 1501 12000 0 21100
rigidLink beam 100 1501
# Geometric transformation command
geomTransf PDelta 495 1.0 0.0 -0.0
element forceBeamColumn 495 1500 1501 495 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 192), with Mesh Node = 193 (auxiliary for element 496)
node 1502 16000 0 18200
rigidLink beam 193 1502


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 100), with Mesh Node = 101 (auxiliary for element 496)
node 1503 16000 0 21100
rigidLink beam 101 1503
# Geometric transformation command
geomTransf PDelta 496 1.0 0.0 -0.0
element forceBeamColumn 496 1502 1503 496 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 105), with Mesh Node = 106 (auxiliary for element 497)
node 1504 16200 9000 21300
rigidLink beam 283 1504

# Extra nodes for zeroLength
# node tag x y z
node 1505 16200 9000 21300
node 1506 20000 9000 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 497 0.0 0.0 1.0
element elasticBeamColumn 497 1505 1506 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 497

# zero_length_elements zeroLength
element zeroLength 1890 1504 1505 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1891 1506 26 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 97), with Mesh Node = 98 (auxiliary for element 498)
node 1507 16200 14500 21300
rigidLink beam 275 1507


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 122), with Mesh Node = 123 (auxiliary for element 498)
node 1508 19800 14500 21300
rigidLink beam 300 1508

# Extra nodes for zeroLength
# node tag x y z
node 1509 16200 14500 21300
node 1510 19800 14500 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 498 0.0 0.0 1.0
element elasticBeamColumn 498 1509 1510 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 498

# zero_length_elements zeroLength
element zeroLength 1892 1507 1509 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1893 1510 1508 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 203), with Mesh Node = 204 (auxiliary for element 499)
node 1511 20000 5500 21100
rigidLink beam 204 1511
# Geometric transformation command
geomTransf PDelta 499 1.0 0.0 -0.0
element forceBeamColumn 499 15 1511 499 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 98), with Mesh Node = 99 (auxiliary for element 500)
node 1512 12000 5500 21100
rigidLink beam 99 1512
# Geometric transformation command
geomTransf PDelta 500 1.0 0.0 -0.0
element forceBeamColumn 500 13 1512 500 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 190), with Mesh Node = 191 (auxiliary for element 501)
node 1513 8000 0 18200
rigidLink beam 191 1513


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 101), with Mesh Node = 102 (auxiliary for element 501)
node 1514 8000 0 21100
rigidLink beam 102 1514
# Geometric transformation command
geomTransf PDelta 501 1.0 0.0 -0.0
element forceBeamColumn 501 1513 1514 501 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 188), with Mesh Node = 189 (auxiliary for element 502)
node 1515 16000 5500 18200
rigidLink beam 189 1515
# Geometric transformation command
geomTransf PDelta 502 1.0 0.0 -0.0
element forceBeamColumn 502 1515 14 502 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 194), with Mesh Node = 195 (auxiliary for element 503)
node 1516 20000 0 18200
rigidLink beam 195 1516


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 102), with Mesh Node = 103 (auxiliary for element 503)
node 1517 20000 0 21100
rigidLink beam 103 1517
# Geometric transformation command
geomTransf PDelta 503 1.0 0.0 -0.0
element forceBeamColumn 503 1516 1517 503 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 198), with Mesh Node = 199 (auxiliary for element 504)
node 1518 20000 0 24800
rigidLink beam 199 1518


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 202), with Mesh Node = 203 (auxiliary for element 504)
node 1519 20000 0 27700
rigidLink beam 203 1519
# Geometric transformation command
geomTransf PDelta 504 1.0 0.0 -0.0
element forceBeamColumn 504 1518 1519 504 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 98), with Mesh Node = 99 (auxiliary for element 505)
node 1520 12000 5500 21500
rigidLink beam 99 1520
# Geometric transformation command
geomTransf PDelta 505 1.0 0.0 -0.0
element forceBeamColumn 505 1520 19 505 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 102), with Mesh Node = 103 (auxiliary for element 506)
node 1521 20000 0 21500
rigidLink beam 103 1521


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 198), with Mesh Node = 199 (auxiliary for element 506)
node 1522 20000 0 24400
rigidLink beam 199 1522
# Geometric transformation command
geomTransf PDelta 506 1.0 0.0 -0.0
element forceBeamColumn 506 1521 1522 506 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 199), with Mesh Node = 200 (auxiliary for element 507)
node 1523 16000 5500 24400
rigidLink beam 200 1523
# Geometric transformation command
geomTransf PDelta 507 1.0 0.0 -0.0
element forceBeamColumn 507 14 1523 507 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 128), with Mesh Node = 129 (auxiliary for element 508)
node 1524 12000 5500 27700
rigidLink beam 129 1524
# Geometric transformation command
geomTransf PDelta 508 1.0 0.0 -0.0
element forceBeamColumn 508 19 1524 508 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 203), with Mesh Node = 204 (auxiliary for element 509)
node 1525 20000 5700 21300
rigidLink beam 369 1525

# Extra nodes for zeroLength
# node tag x y z
node 1526 20000 5700 21300
node 1527 20000 9000 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 509 0.0 -0.0 1.0
element elasticBeamColumn 509 1526 1527 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 509

# zero_length_elements zeroLength
element zeroLength 1894 1525 1526 -mat 5 5 5 5 51 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1895 1527 26 -mat 5 5 5 5 51 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 101), with Mesh Node = 102 (auxiliary for element 510)
node 1528 8200 0 21300
rigidLink beam 279 1528


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 99), with Mesh Node = 100 (auxiliary for element 510)
node 1529 11800 0 21300
rigidLink beam 277 1529

# Extra nodes for zeroLength
# node tag x y z
node 1530 8200 0 21300
node 1531 11800 0 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 510 0.0 0.0 1.0
element elasticBeamColumn 510 1530 1531 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 510

# zero_length_elements zeroLength
element zeroLength 1896 1528 1530 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1897 1531 1529 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 105), with Mesh Node = 106 (auxiliary for element 511)
node 1532 16000 8800 21300
rigidLink beam 283 1532

# Extra nodes for zeroLength
# node tag x y z
node 1533 16000 5500 21300
node 1534 16000 8800 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 511 0.0 -0.0 1.0
element elasticBeamColumn 511 1533 1534 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 511

# zero_length_elements zeroLength
element zeroLength 1898 14 1533 -mat 5 5 5 5 51 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1899 1534 1532 -mat 5 5 5 5 51 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 203), with Mesh Node = 204 (auxiliary for element 512)
node 1535 19800 5500 21300
rigidLink beam 369 1535

# Extra nodes for zeroLength
# node tag x y z
node 1536 16000 5500 21300
node 1537 19800 5500 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 512 0.0 0.0 1.0
element elasticBeamColumn 512 1536 1537 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 512

# zero_length_elements zeroLength
element zeroLength 1900 14 1536 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1901 1537 1535 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 99), with Mesh Node = 100 (auxiliary for element 513)
node 1538 12200 0 21300
rigidLink beam 277 1538


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 100), with Mesh Node = 101 (auxiliary for element 513)
node 1539 15800 0 21300
rigidLink beam 278 1539

# Extra nodes for zeroLength
# node tag x y z
node 1540 12200 0 21300
node 1541 15800 0 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 513 0.0 0.0 1.0
element elasticBeamColumn 513 1540 1541 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 513

# zero_length_elements zeroLength
element zeroLength 1902 1538 1540 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1903 1541 1539 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 102), with Mesh Node = 103 (auxiliary for element 514)
node 1542 20000 200 21300
rigidLink beam 280 1542


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 203), with Mesh Node = 204 (auxiliary for element 514)
node 1543 20000 5300 21300
rigidLink beam 369 1543

# Extra nodes for zeroLength
# node tag x y z
node 1544 20000 200 21300
node 1545 20000 5300 21300

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 514 0.0 -0.0 1.0
element elasticBeamColumn 514 1544 1545 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 514

# zero_length_elements zeroLength
element zeroLength 1904 1542 1544 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1905 1545 1543 -mat 5 5 5 5 49 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 108), with Mesh Node = 109 (auxiliary for element 515)
node 1546 16000 14300 24600
rigidLink beam 286 1546

# Extra nodes for zeroLength
# node tag x y z
node 1547 16000 9000 24600
node 1548 16000 14300 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 515 0.0 -0.0 1.0
element elasticBeamColumn 515 1547 1548 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 515

# zero_length_elements zeroLength
element zeroLength 1906 44 1547 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1907 1548 1546 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 199), with Mesh Node = 200 (auxiliary for element 516)
node 1549 16000 5700 24600
rigidLink beam 365 1549

# Extra nodes for zeroLength
# node tag x y z
node 1550 16000 5700 24600
node 1551 16000 9000 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 516 0.0 -0.0 1.0
element elasticBeamColumn 516 1550 1551 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 516

# zero_length_elements zeroLength
element zeroLength 1908 1549 1550 -mat 5 5 5 5 53 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1909 1551 44 -mat 5 5 5 5 53 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 121), with Mesh Node = 122 (auxiliary for element 517)
node 1552 12000 8800 24600
rigidLink beam 299 1552

# Extra nodes for zeroLength
# node tag x y z
node 1553 12000 5500 24600
node 1554 12000 8800 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 517 0.0 -0.0 1.0
element elasticBeamColumn 517 1553 1554 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 517

# zero_length_elements zeroLength
element zeroLength 1910 19 1553 -mat 5 5 5 5 53 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1911 1554 1552 -mat 5 5 5 5 53 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 120), with Mesh Node = 121 (auxiliary for element 518)
node 1555 8200 5500 24600
rigidLink beam 298 1555

# Extra nodes for zeroLength
# node tag x y z
node 1556 8200 5500 24600
node 1557 12000 5500 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 518 0.0 0.0 1.0
element elasticBeamColumn 518 1556 1557 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 518

# zero_length_elements zeroLength
element zeroLength 1912 1555 1556 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1913 1557 19 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 120), with Mesh Node = 121 (auxiliary for element 519)
node 1558 8000 5700 24600
rigidLink beam 298 1558

# Extra nodes for zeroLength
# node tag x y z
node 1559 8000 5700 24600
node 1560 8000 9000 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 519 0.0 -0.0 1.0
element elasticBeamColumn 519 1559 1560 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 519

# zero_length_elements zeroLength
element zeroLength 1914 1558 1559 -mat 5 5 5 5 53 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1915 1560 43 -mat 5 5 5 5 53 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 121), with Mesh Node = 122 (auxiliary for element 520)
node 1561 12200 9000 24600
rigidLink beam 299 1561

# Extra nodes for zeroLength
# node tag x y z
node 1562 12200 9000 24600
node 1563 16000 9000 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 520 0.0 0.0 1.0
element elasticBeamColumn 520 1562 1563 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 520

# zero_length_elements zeroLength
element zeroLength 1916 1561 1562 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1917 1563 44 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 121), with Mesh Node = 122 (auxiliary for element 521)
node 1564 11800 9000 24600
rigidLink beam 299 1564

# Extra nodes for zeroLength
# node tag x y z
node 1565 8000 9000 24600
node 1566 11800 9000 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 521 0.0 0.0 1.0
element elasticBeamColumn 521 1565 1566 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 521

# zero_length_elements zeroLength
element zeroLength 1918 43 1565 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1919 1566 1564 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 197), with Mesh Node = 198 (auxiliary for element 522)
node 1567 19800 9000 24600
rigidLink beam 363 1567

# Extra nodes for zeroLength
# node tag x y z
node 1568 16000 9000 24600
node 1569 19800 9000 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 522 0.0 0.0 1.0
element elasticBeamColumn 522 1568 1569 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 522

# zero_length_elements zeroLength
element zeroLength 1920 44 1568 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1921 1569 1567 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 120), with Mesh Node = 121 (auxiliary for element 523)
node 1570 7800 5500 24600
rigidLink beam 298 1570

# Extra nodes for zeroLength
# node tag x y z
node 1571 4000 5500 24600
node 1572 7800 5500 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 523 0.0 0.0 1.0
element elasticBeamColumn 523 1571 1572 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 523

# zero_length_elements zeroLength
element zeroLength 1922 20 1571 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1923 1572 1570 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 200), with Mesh Node = 201 (auxiliary for element 524)
node 1573 15800 9000 27900
rigidLink beam 366 1573

# Extra nodes for zeroLength
# node tag x y z
node 1574 12000 9000 27900
node 1575 15800 9000 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 524 0.0 0.0 1.0
element elasticBeamColumn 524 1574 1575 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 524

# zero_length_elements zeroLength
element zeroLength 1924 45 1574 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1925 1575 1573 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 200), with Mesh Node = 201 (auxiliary for element 525)
node 1576 16200 9000 27900
rigidLink beam 366 1576

# Extra nodes for zeroLength
# node tag x y z
node 1577 16200 9000 27900
node 1578 20000 9000 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 525 0.0 0.0 1.0
element elasticBeamColumn 525 1577 1578 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 525

# zero_length_elements zeroLength
element zeroLength 1926 1576 1577 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1927 1578 46 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 116), with Mesh Node = 117 (auxiliary for element 526)
node 1579 8200 9000 27900
rigidLink beam 294 1579

# Extra nodes for zeroLength
# node tag x y z
node 1580 8200 9000 27900
node 1581 12000 9000 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 526 0.0 0.0 1.0
element elasticBeamColumn 526 1580 1581 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 526

# zero_length_elements zeroLength
element zeroLength 1928 1579 1580 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1929 1581 45 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 135), with Mesh Node = 136 (auxiliary for element 527)
node 1582 0 5500 24800
rigidLink beam 136 1582
# Geometric transformation command
geomTransf PDelta 527 1.0 0.0 -0.0
element forceBeamColumn 527 1582 23 527 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 134), with Mesh Node = 135 (auxiliary for element 528)
node 1583 4000 9000 24800
rigidLink beam 135 1583
# Geometric transformation command
geomTransf PDelta 528 1.0 0.0 -0.0
element forceBeamColumn 528 1583 47 528 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 201), with Mesh Node = 202 (auxiliary for element 529)
node 1584 20000 5500 27700
rigidLink beam 202 1584
# Geometric transformation command
geomTransf PDelta 529 1.0 0.0 -0.0
element forceBeamColumn 529 21 1584 529 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 203), with Mesh Node = 204 (auxiliary for element 530)
node 1585 20000 5500 21500
rigidLink beam 204 1585
# Geometric transformation command
geomTransf PDelta 530 1.0 0.0 -0.0
element forceBeamColumn 530 1585 21 530 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 197), with Mesh Node = 198 (auxiliary for element 531)
node 1586 20000 9000 24800
rigidLink beam 198 1586
# Geometric transformation command
geomTransf PDelta 531 1.0 0.0 -0.0
element forceBeamColumn 531 1586 46 531 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 129), with Mesh Node = 130 (auxiliary for element 532)
node 1587 16000 200 24600
rigidLink beam 307 1587


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 199), with Mesh Node = 200 (auxiliary for element 532)
node 1588 16000 5300 24600
rigidLink beam 365 1588

# Extra nodes for zeroLength
# node tag x y z
node 1589 16000 200 24600
node 1590 16000 5300 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 532 0.0 -0.0 1.0
element elasticBeamColumn 532 1589 1590 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 532

# zero_length_elements zeroLength
element zeroLength 1930 1587 1589 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1931 1590 1588 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 126), with Mesh Node = 127 (auxiliary for element 533)
node 1591 12000 200 24600
rigidLink beam 304 1591

# Extra nodes for zeroLength
# node tag x y z
node 1592 12000 200 24600
node 1593 12000 5500 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 533 0.0 -0.0 1.0
element elasticBeamColumn 533 1592 1593 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 533

# zero_length_elements zeroLength
element zeroLength 1932 1591 1592 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1933 1593 19 -mat 5 5 5 5 52 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 126), with Mesh Node = 127 (auxiliary for element 534)
node 1594 12200 0 24600
rigidLink beam 304 1594


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 129), with Mesh Node = 130 (auxiliary for element 534)
node 1595 15800 0 24600
rigidLink beam 307 1595

# Extra nodes for zeroLength
# node tag x y z
node 1596 12200 0 24600
node 1597 15800 0 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 534 0.0 0.0 1.0
element elasticBeamColumn 534 1596 1597 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 534

# zero_length_elements zeroLength
element zeroLength 1934 1594 1596 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1935 1597 1595 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 198), with Mesh Node = 199 (auxiliary for element 535)
node 1598 19800 0 24600
rigidLink beam 364 1598


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 129), with Mesh Node = 130 (auxiliary for element 535)
node 1599 16200 0 24600
rigidLink beam 307 1599

# Extra nodes for zeroLength
# node tag x y z
node 1600 19800 0 24600
node 1601 16200 0 24600

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 535 0.0 0.0 1.0
element elasticBeamColumn 535 1600 1601 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 535

# zero_length_elements zeroLength
element zeroLength 1936 1598 1600 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient -1.0 0.0 0.0 0.0 -1.0 0.0
element zeroLength 1937 1601 1599 -mat 5 5 5 5 31 5 -dir 1 2 3 4 5 6 -orient -1.0 0.0 0.0 0.0 -1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 199), with Mesh Node = 200 (auxiliary for element 536)
node 1602 16000 5500 24800
rigidLink beam 200 1602
# Geometric transformation command
geomTransf PDelta 536 1.0 0.0 -0.0
element forceBeamColumn 536 1602 24 536 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 127), with Mesh Node = 128 (auxiliary for element 537)
node 1603 12200 0 27900
rigidLink beam 305 1603


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 131), with Mesh Node = 132 (auxiliary for element 537)
node 1604 15800 0 27900
rigidLink beam 309 1604

# Extra nodes for zeroLength
# node tag x y z
node 1605 12200 0 27900
node 1606 15800 0 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 537 0.0 0.0 1.0
element elasticBeamColumn 537 1605 1606 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 537

# zero_length_elements zeroLength
element zeroLength 1938 1603 1605 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1939 1606 1604 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 131), with Mesh Node = 132 (auxiliary for element 538)
node 1607 16200 0 27900
rigidLink beam 309 1607


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 202), with Mesh Node = 203 (auxiliary for element 538)
node 1608 19800 0 27900
rigidLink beam 368 1608

# Extra nodes for zeroLength
# node tag x y z
node 1609 16200 0 27900
node 1610 19800 0 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 538 0.0 0.0 1.0
element elasticBeamColumn 538 1609 1610 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 538

# zero_length_elements zeroLength
element zeroLength 1940 1607 1609 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1941 1610 1608 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 131), with Mesh Node = 132 (auxiliary for element 539)
node 1611 16000 200 27900
rigidLink beam 309 1611

# Extra nodes for zeroLength
# node tag x y z
node 1612 16000 200 27900
node 1613 16000 5500 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 539 0.0 -0.0 1.0
element elasticBeamColumn 539 1612 1613 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 539

# zero_length_elements zeroLength
element zeroLength 1942 1611 1612 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1943 1613 24 -mat 5 5 5 5 47 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 170), with Mesh Node = 171 (auxiliary for element 540)
node 1614 16000 0 4600
rigidLink beam 171 1614
# Geometric transformation command
geomTransf PDelta 540 1.0 0.0 -0.0
element forceBeamColumn 540 205 1614 540 HingeRadau 6 200.0 6 200.0 7


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 173), with Mesh Node = 174 (auxiliary for element 541)
node 1615 16000 14500 4600
rigidLink beam 174 1615
# Geometric transformation command
geomTransf PDelta 541 1.0 0.0 -0.0
element forceBeamColumn 541 206 1615 541 HingeRadau 6 200.0 6 200.0 7


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 175), with Mesh Node = 176 (auxiliary for element 542)
node 1616 20000 14500 4600
rigidLink beam 176 1616
# Geometric transformation command
geomTransf PDelta 542 1.0 0.0 -0.0
element forceBeamColumn 542 207 1616 542 HingeRadau 6 200.0 6 200.0 7


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 180), with Mesh Node = 181 (auxiliary for element 543)
node 1617 0 14500 4600
rigidLink beam 181 1617
# Geometric transformation command
geomTransf PDelta 543 1.0 0.0 -0.0
element forceBeamColumn 543 208 1617 543 HingeRadau 6 200.0 6 200.0 7


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 169), with Mesh Node = 170 (auxiliary for element 544)
node 1618 0 0 4600
rigidLink beam 170 1618
# Geometric transformation command
geomTransf PDelta 544 1.0 0.0 -0.0
element forceBeamColumn 544 209 1618 544 HingeRadau 6 200.0 6 200.0 7
# Geometric transformation command
geomTransf PDelta 545 1.0 0.0 -0.0
element forceBeamColumn 545 210 34 545 HingeRadau 6 200.0 6 200.0 7
# Geometric transformation command
geomTransf PDelta 546 1.0 0.0 -0.0
element forceBeamColumn 546 211 28 546 HingeRadau 6 200.0 6 200.0 7


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 195), with Mesh Node = 196 (auxiliary for element 547)
node 1619 20000 0 4600
rigidLink beam 196 1619
# Geometric transformation command
geomTransf PDelta 547 1.0 0.0 -0.0
element forceBeamColumn 547 212 1619 547 HingeRadau 6 200.0 6 200.0 7


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 167), with Mesh Node = 168 (auxiliary for element 548)
node 1620 12000 0 4600
rigidLink beam 168 1620
# Geometric transformation command
geomTransf PDelta 548 1.0 0.0 -0.0
element forceBeamColumn 548 213 1620 548 HingeRadau 6 200.0 6 200.0 7


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 156), with Mesh Node = 157 (auxiliary for element 549)
node 1621 0 8800 8100
rigidLink beam 323 1621

# Extra nodes for zeroLength
# node tag x y z
node 1622 0 5500 8100
node 1623 0 8800 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 549 0.0 -0.0 1.0
element elasticBeamColumn 549 1622 1623 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 549

# zero_length_elements zeroLength
element zeroLength 1944 5 1622 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1945 1623 1621 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 179), with Mesh Node = 180 (auxiliary for element 550)
node 1624 0 200 8100
rigidLink beam 346 1624

# Extra nodes for zeroLength
# node tag x y z
node 1625 0 200 8100
node 1626 0 5500 8100

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 550 0.0 -0.0 1.0
element elasticBeamColumn 550 1625 1626 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 550

# zero_length_elements zeroLength
element zeroLength 1946 1624 1625 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1947 1626 5 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 187), with Mesh Node = 188 (auxiliary for element 551)
node 1627 20000 0 14900
rigidLink beam 188 1627


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 194), with Mesh Node = 195 (auxiliary for element 551)
node 1628 20000 0 17800
rigidLink beam 195 1628
# Geometric transformation command
geomTransf PDelta 551 1.0 0.0 -0.0
element forceBeamColumn 551 1627 1628 551 HingeRadau 20 200.0 20 200.0 21


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 196), with Mesh Node = 197 (auxiliary for element 552)
node 1629 20000 0 8300
rigidLink beam 197 1629


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 165), with Mesh Node = 166 (auxiliary for element 552)
node 1630 20000 0 11200
rigidLink beam 166 1630
# Geometric transformation command
geomTransf PDelta 552 1.0 0.0 -0.0
element forceBeamColumn 552 1629 1630 552 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 165), with Mesh Node = 166 (auxiliary for element 553)
node 1631 20000 0 11600
rigidLink beam 166 1631


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 187), with Mesh Node = 188 (auxiliary for element 553)
node 1632 20000 0 14500
rigidLink beam 188 1632
# Geometric transformation command
geomTransf PDelta 553 1.0 0.0 -0.0
element forceBeamColumn 553 1631 1632 553 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 164), with Mesh Node = 165 (auxiliary for element 554)
node 1633 12000 5500 14900
rigidLink beam 165 1633
# Geometric transformation command
geomTransf PDelta 554 1.0 0.0 -0.0
element forceBeamColumn 554 1633 13 554 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 170), with Mesh Node = 171 (auxiliary for element 555)
node 1634 16200 0 4800
rigidLink beam 337 1634


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 195), with Mesh Node = 196 (auxiliary for element 555)
node 1635 19800 0 4800
rigidLink beam 361 1635

# Extra nodes for zeroLength
# node tag x y z
node 1636 16200 0 4800
node 1637 19800 0 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 555 0.0 0.0 1.0
element elasticBeamColumn 555 1636 1637 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 555

# zero_length_elements zeroLength
element zeroLength 1948 1634 1636 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1949 1637 1635 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 177), with Mesh Node = 178 (auxiliary for element 556)
node 1638 12200 9000 18000
rigidLink beam 344 1638

# Extra nodes for zeroLength
# node tag x y z
node 1639 12200 9000 18000
node 1640 16000 9000 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 556 0.0 0.0 1.0
element elasticBeamColumn 556 1639 1640 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 556

# zero_length_elements zeroLength
element zeroLength 1950 1638 1639 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1951 1640 40 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 184), with Mesh Node = 185 (auxiliary for element 557)
node 1641 19800 9000 18000
rigidLink beam 351 1641

# Extra nodes for zeroLength
# node tag x y z
node 1642 16000 9000 18000
node 1643 19800 9000 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 557 0.0 0.0 1.0
element elasticBeamColumn 557 1642 1643 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 557

# zero_length_elements zeroLength
element zeroLength 1952 40 1642 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1953 1643 1641 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 179), with Mesh Node = 180 (auxiliary for element 558)
node 1644 0 0 8300
rigidLink beam 180 1644
# Geometric transformation command
geomTransf PDelta 558 1.0 0.0 -0.0
element forceBeamColumn 558 1644 16 558 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 180), with Mesh Node = 181 (auxiliary for element 559)
node 1645 0 14300 4800
rigidLink beam 347 1645

# Extra nodes for zeroLength
# node tag x y z
node 1646 0 9000 4800
node 1647 0 14300 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 559 0.0 -0.0 1.0
element elasticBeamColumn 559 1646 1647 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 559

# zero_length_elements zeroLength
element zeroLength 1954 34 1646 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1955 1647 1645 -mat 5 5 5 5 56 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 183), with Mesh Node = 184 (auxiliary for element 560)
node 1648 20000 5500 14900
rigidLink beam 184 1648
# Geometric transformation command
geomTransf PDelta 560 1.0 0.0 -0.0
element forceBeamColumn 560 1648 15 560 HingeRadau 14 200.0 14 200.0 17


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 192), with Mesh Node = 193 (auxiliary for element 561)
node 1649 16200 0 18000
rigidLink beam 359 1649


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 194), with Mesh Node = 195 (auxiliary for element 561)
node 1650 19800 0 18000
rigidLink beam 360 1650

# Extra nodes for zeroLength
# node tag x y z
node 1651 16200 0 18000
node 1652 19800 0 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 561 0.0 0.0 1.0
element elasticBeamColumn 561 1651 1652 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 561

# zero_length_elements zeroLength
element zeroLength 1956 1649 1651 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1957 1652 1650 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 192), with Mesh Node = 193 (auxiliary for element 562)
node 1653 16000 200 18000
rigidLink beam 359 1653


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 188), with Mesh Node = 189 (auxiliary for element 562)
node 1654 16000 5300 18000
rigidLink beam 355 1654

# Extra nodes for zeroLength
# node tag x y z
node 1655 16000 200 18000
node 1656 16000 5300 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 562 0.0 -0.0 1.0
element elasticBeamColumn 562 1655 1656 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 562

# zero_length_elements zeroLength
element zeroLength 1958 1653 1655 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1959 1656 1654 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 189), with Mesh Node = 190 (auxiliary for element 563)
node 1657 12200 0 18000
rigidLink beam 356 1657


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 192), with Mesh Node = 193 (auxiliary for element 563)
node 1658 15800 0 18000
rigidLink beam 359 1658

# Extra nodes for zeroLength
# node tag x y z
node 1659 12200 0 18000
node 1660 15800 0 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 563 0.0 0.0 1.0
element elasticBeamColumn 563 1659 1660 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 563

# zero_length_elements zeroLength
element zeroLength 1960 1657 1659 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1961 1660 1658 -mat 5 5 5 5 30 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 189), with Mesh Node = 190 (auxiliary for element 564)
node 1661 12000 200 18000
rigidLink beam 356 1661

# Extra nodes for zeroLength
# node tag x y z
node 1662 12000 200 18000
node 1663 12000 5500 18000

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 564 0.0 -0.0 1.0
element elasticBeamColumn 564 1662 1663 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 564

# zero_length_elements zeroLength
element zeroLength 1962 1661 1662 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1963 1663 13 -mat 5 5 5 5 54 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 200), with Mesh Node = 201 (auxiliary for element 565)
node 1664 16000 9000 27700
rigidLink beam 201 1664
# Geometric transformation command
geomTransf PDelta 565 1.0 0.0 -0.0
element forceBeamColumn 565 44 1664 565 HingeRadau 18 200.0 18 200.0 19


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 200), with Mesh Node = 201 (auxiliary for element 566)
node 1665 16000 8800 27900
rigidLink beam 366 1665

# Extra nodes for zeroLength
# node tag x y z
node 1666 16000 5500 27900
node 1667 16000 8800 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 566 0.0 -0.0 1.0
element elasticBeamColumn 566 1666 1667 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 566

# zero_length_elements zeroLength
element zeroLength 1964 24 1666 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1965 1667 1665 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 201), with Mesh Node = 202 (auxiliary for element 567)
node 1668 20000 5700 27900
rigidLink beam 367 1668

# Extra nodes for zeroLength
# node tag x y z
node 1669 20000 5700 27900
node 1670 20000 9000 27900

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 567 0.0 -0.0 1.0
element elasticBeamColumn 567 1669 1670 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 567

# zero_length_elements zeroLength
element zeroLength 1966 1668 1669 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1967 1670 46 -mat 5 5 5 5 32 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# truss_elements truss
element truss 568 3 71 1.0 95
element truss 569 59 48 1.0 95
element truss 570 50 48 1.0 97
element truss 571 58 169 1.0 95
element truss 572 110 26 1.0 91
element truss 573 21 103 1.0 91
element truss 574 125 198 1.0 91
element truss 575 46 110 1.0 91
element truss 576 198 123 1.0 91
element truss 577 199 204 1.0 91
element truss 578 15 188 1.0 91
element truss 579 123 185 1.0 91
element truss 580 204 195 1.0 91
element truss 581 195 184 1.0 91
element truss 582 26 126 1.0 91
element truss 583 103 15 1.0 91
element truss 584 126 25 1.0 91
element truss 585 25 67 1.0 91
element truss 586 184 166 1.0 91
element truss 587 185 177 1.0 91
element truss 588 177 65 1.0 91
element truss 589 188 10 1.0 91
element truss 590 65 155 1.0 91
element truss 591 10 197 1.0 91
element truss 592 166 55 1.0 91
element truss 593 197 28 1.0 91
element truss 594 67 27 1.0 91
element truss 595 55 196 1.0 91
element truss 596 27 176 1.0 91
element truss 597 155 64 1.0 91
element truss 598 36 7 1.0 97
element truss 599 9 36 1.0 97
element truss 600 62 164 1.0 97
element truss 601 14 40 1.0 97
element truss 602 189 62 1.0 97
element truss 603 40 9 1.0 97
element truss 604 200 106 1.0 97
element truss 605 106 189 1.0 97
element truss 606 201 200 1.0 97
element truss 607 24 44 1.0 97
element truss 608 44 14 1.0 97
element truss 609 172 49 1.0 95
element truss 610 1 91 1.0 95
element truss 611 90 1 1.0 95
element truss 612 74 172 1.0 95
element truss 613 175 156 1.0 95
element truss 614 4 182 1.0 95
element truss 615 30 90 1.0 95
element truss 616 79 175 1.0 95
element truss 617 53 76 1.0 95
element truss 618 81 30 1.0 95
element truss 619 84 4 1.0 95
element truss 620 76 74 1.0 95
element truss 621 12 84 1.0 95
element truss 622 87 79 1.0 95
element truss 623 114 53 1.0 95
element truss 624 94 12 1.0 95
element truss 625 162 3 1.0 95
element truss 626 29 81 1.0 95
element truss 627 47 107 1.0 95
element truss 628 107 29 1.0 95
element truss 629 134 135 1.0 95
element truss 630 115 87 1.0 95
element truss 631 135 114 1.0 95
element truss 632 95 115 1.0 95
element truss 633 20 94 1.0 95
element truss 634 118 95 1.0 95
element truss 635 116 20 1.0 95
element truss 636 70 59 1.0 95
element truss 637 33 51 1.0 95
element truss 638 183 70 1.0 95
element truss 639 173 33 1.0 95
element truss 640 51 31 1.0 95
element truss 641 50 77 1.0 95
element truss 642 160 50 1.0 95
element truss 643 52 160 1.0 95
element truss 644 191 8 1.0 95
element truss 645 83 183 1.0 95
element truss 646 8 162 1.0 95
element truss 647 38 173 1.0 95
element truss 648 85 52 1.0 95
element truss 649 17 191 1.0 95
element truss 650 120 17 1.0 95
element truss 651 102 83 1.0 95
element truss 652 121 102 1.0 95
element truss 653 105 85 1.0 95
element truss 654 97 38 1.0 95
element truss 655 117 104 1.0 95
element truss 656 104 105 1.0 95
element truss 657 140 43 1.0 95
element truss 658 131 121 1.0 95
element truss 659 43 97 1.0 95
element truss 660 22 120 1.0 95
element truss 661 133 44 1.0 95
element truss 662 24 130 1.0 95
element truss 663 164 57 1.0 97
element truss 664 201 109 1.0 95
element truss 665 182 170 1.0 87
element truss 666 156 49 1.0 97
element truss 667 202 199 1.0 91
element truss 668 57 64 1.0 89
element truss 669 179 34 1.0 91
element truss 670 155 174 1.0 87
element truss 671 157 181 1.0 91
element truss 672 23 42 1.0 93
element truss 673 55 54 1.0 89
element truss 674 7 28 1.0 89
element truss 675 203 21 1.0 91
element truss 676 202 198 1.0 93
element truss 677 7 61 1.0 97
element truss 678 27 61 1.0 89
element truss 679 138 136 1.0 93
element truss 680 56 163 1.0 97
element truss 681 35 169 1.0 97
element truss 682 57 54 1.0 97
element truss 683 60 54 1.0 95
element truss 684 7 171 1.0 95
element truss 685 118 135 1.0 97
element truss 686 47 20 1.0 97
element truss 687 156 72 1.0 95
element truss 688 182 2 1.0 95
element truss 689 46 21 1.0 93
element truss 690 100 13 1.0 95
element truss 691 99 190 1.0 95
element truss 692 63 56 1.0 97
element truss 693 13 186 1.0 95
element truss 694 190 165 1.0 95
element truss 695 41 86 1.0 95
element truss 696 96 178 1.0 95
element truss 697 45 108 1.0 95
element truss 698 19 100 1.0 95
element truss 699 124 122 1.0 95
element truss 700 129 127 1.0 95
element truss 701 127 99 1.0 95
element truss 702 128 19 1.0 95
element truss 703 165 63 1.0 97
element truss 704 13 37 1.0 97
element truss 705 132 200 1.0 95
element truss 706 122 96 1.0 95
element truss 707 37 6 1.0 97
element truss 708 108 41 1.0 95
element truss 709 122 99 1.0 97
element truss 710 99 178 1.0 97
element truss 711 129 122 1.0 97
element truss 712 41 13 1.0 97
element truss 713 178 165 1.0 97
element truss 714 158 7 1.0 95
element truss 715 19 41 1.0 97
element truss 716 45 19 1.0 97
element truss 717 36 153 1.0 95
element truss 718 164 60 1.0 95
element truss 719 66 57 1.0 95
element truss 720 187 164 1.0 95
element truss 721 62 66 1.0 95
element truss 722 68 36 1.0 95
element truss 723 153 61 1.0 95
element truss 724 9 158 1.0 95
element truss 725 57 174 1.0 95
element truss 726 192 62 1.0 95
element truss 727 14 193 1.0 95
element truss 728 40 68 1.0 95
element truss 729 193 9 1.0 95
element truss 730 101 189 1.0 95
element truss 731 189 187 1.0 95
element truss 732 200 101 1.0 95
element truss 733 109 106 1.0 95
element truss 734 98 40 1.0 95
element truss 735 106 192 1.0 95
element truss 736 44 98 1.0 95
element truss 737 130 14 1.0 95
element truss 738 38 8 1.0 97
element truss 739 52 70 1.0 97
element truss 740 33 3 1.0 97
element truss 741 8 33 1.0 97
element truss 742 161 56 1.0 95
element truss 743 83 52 1.0 97
element truss 744 70 50 1.0 97
element truss 745 105 83 1.0 97
element truss 746 17 38 1.0 97
element truss 747 43 17 1.0 97
element truss 748 121 105 1.0 97
element truss 749 22 43 1.0 97
element truss 750 63 154 1.0 95
element truss 751 69 35 1.0 95
element truss 752 6 58 1.0 95
element truss 753 154 163 1.0 95
element truss 754 117 121 1.0 97
element truss 755 35 167 1.0 95
element truss 756 159 63 1.0 95
element truss 757 37 69 1.0 95
element truss 758 6 35 1.0 97
element truss 759 186 6 1.0 95
element truss 760 86 37 1.0 95
element truss 761 165 161 1.0 95
element truss 762 178 159 1.0 95
element truss 763 56 168 1.0 95
element truss 764 191 186 1.0 87
element truss 765 193 186 1.0 87
element truss 766 87 93 1.0 87
element truss 767 190 183 1.0 87
element truss 768 87 183 1.0 87
element truss 769 153 167 1.0 87
element truss 770 113 87 1.0 87
element truss 771 92 84 1.0 87
element truss 772 191 84 1.0 87
element truss 773 102 87 1.0 87
element truss 774 100 191 1.0 87
element truss 775 102 190 1.0 87
element truss 776 94 92 1.0 87
element truss 777 94 191 1.0 87
element truss 778 154 174 1.0 87
element truss 779 103 193 1.0 87
element truss 780 137 94 1.0 87
element truss 781 101 195 1.0 87
element truss 782 100 193 1.0 87
element truss 783 101 190 1.0 87
element truss 784 95 102 1.0 87
element truss 785 95 113 1.0 87
element truss 786 120 100 1.0 87
element truss 787 127 102 1.0 87
element truss 788 120 94 1.0 87
element truss 789 132 199 1.0 87
element truss 790 199 101 1.0 87
element truss 791 130 103 1.0 87
element truss 792 203 130 1.0 87
element truss 793 154 77 1.0 87
element truss 794 127 101 1.0 87
element truss 795 130 100 1.0 87
element truss 796 132 127 1.0 87
element truss 797 128 130 1.0 87
element truss 798 128 120 1.0 87
element truss 799 116 120 1.0 87
element truss 800 131 127 1.0 87
element truss 801 131 95 1.0 87
element truss 802 51 91 1.0 87
element truss 803 116 137 1.0 87
element truss 804 141 95 1.0 87
element truss 805 51 167 1.0 87
element truss 806 179 91 1.0 87
element truss 807 172 77 1.0 87
element truss 808 172 181 1.0 87
element truss 809 90 179 1.0 87
element truss 810 160 172 1.0 87
element truss 811 88 172 1.0 87
element truss 812 160 154 1.0 87
element truss 813 69 51 1.0 87
element truss 814 90 51 1.0 87
element truss 815 67 153 1.0 87
element truss 816 66 154 1.0 87
element truss 817 69 153 1.0 87
element truss 818 66 155 1.0 87
element truss 819 68 69 1.0 87
element truss 820 177 66 1.0 87
element truss 821 159 66 1.0 87
element truss 822 68 67 1.0 87
element truss 823 76 88 1.0 87
element truss 824 173 69 1.0 87
element truss 825 159 160 1.0 87
element truss 826 173 90 1.0 87
element truss 827 76 160 1.0 87
element truss 828 81 173 1.0 87
element truss 829 78 90 1.0 87
element truss 830 81 78 1.0 87
element truss 831 85 76 1.0 87
element truss 832 82 76 1.0 87
element truss 833 58 71 1.0 87
element truss 834 60 168 1.0 87
element truss 835 58 171 1.0 87
element truss 836 86 173 1.0 87
element truss 837 59 168 1.0 87
element truss 838 182 71 1.0 87
element truss 839 59 72 1.0 87
element truss 840 60 196 1.0 87
element truss 841 161 60 1.0 87
element truss 842 158 197 1.0 87
element truss 843 166 60 1.0 87
element truss 844 197 171 1.0 87
element truss 845 162 58 1.0 87
element truss 846 175 59 1.0 87
element truss 847 162 182 1.0 87
element truss 848 161 59 1.0 87
element truss 849 158 58 1.0 87
element truss 850 85 159 1.0 87
element truss 851 183 175 1.0 87
element truss 852 84 16 1.0 87
element truss 853 84 162 1.0 87
element truss 854 175 180 1.0 87
element truss 855 93 175 1.0 87
element truss 856 16 182 1.0 87
element truss 857 186 162 1.0 87
element truss 858 183 161 1.0 87
element truss 859 186 158 1.0 87
element truss 860 187 161 1.0 87
element truss 861 187 166 1.0 87
element truss 862 192 159 1.0 87
element truss 863 188 158 1.0 87
element truss 864 195 187 1.0 87
element truss 865 190 187 1.0 87
element truss 866 193 188 1.0 87
element truss 867 98 86 1.0 87
element truss 868 96 192 1.0 87
element truss 869 126 68 1.0 87
element truss 870 86 68 1.0 87
element truss 871 123 192 1.0 87
element truss 872 98 126 1.0 87
element truss 873 97 86 1.0 87
element truss 874 97 81 1.0 87
element truss 875 114 85 1.0 87
element truss 876 96 85 1.0 87
element truss 877 192 177 1.0 87
element truss 878 104 114 1.0 87
element truss 879 111 81 1.0 87
element truss 880 107 97 1.0 87
element truss 881 107 111 1.0 87
element truss 882 119 114 1.0 87
element truss 883 114 82 1.0 87
element truss 884 109 123 1.0 87
element truss 885 109 96 1.0 87
element truss 886 104 96 1.0 87
element truss 887 108 98 1.0 87
element truss 888 110 98 1.0 87
element truss 889 108 97 1.0 87
element truss 890 140 108 1.0 87
element truss 891 124 109 1.0 87
element truss 892 133 110 1.0 87
element truss 893 125 109 1.0 87
element truss 894 124 104 1.0 87
element truss 895 133 108 1.0 87
element truss 896 134 104 1.0 87
element truss 897 134 119 1.0 87
element truss 898 140 107 1.0 87
element truss 899 139 107 1.0 87
element truss 900 153 176 1.0 87
element truss 901 82 75 1.0 91
element truss 902 5 170 1.0 91
element truss 903 180 73 1.0 91
element truss 904 75 88 1.0 91
element truss 905 78 32 1.0 91
element truss 906 18 92 1.0 91
element truss 907 111 39 1.0 91
element truss 908 39 78 1.0 91
element truss 909 92 11 1.0 91
element truss 910 80 93 1.0 91
element truss 911 113 80 1.0 91
element truss 912 42 18 1.0 93
element truss 913 136 112 1.0 93
element truss 914 138 119 1.0 91
element truss 915 119 112 1.0 91
element truss 916 23 137 1.0 91
element truss 917 112 82 1.0 91
element truss 918 42 111 1.0 91
element truss 919 139 42 1.0 91
element truss 920 141 136 1.0 91
element truss 921 137 18 1.0 91
element truss 922 136 113 1.0 91
element truss 923 112 80 1.0 93
element truss 924 39 11 1.0 93
element truss 925 75 89 1.0 93
element truss 926 11 32 1.0 93
element truss 927 80 75 1.0 93
element truss 928 18 39 1.0 93
element truss 929 89 157 1.0 93
element truss 930 5 34 1.0 93
element truss 931 157 73 1.0 93
element truss 932 32 5 1.0 93
element truss 933 3 169 1.0 89
element truss 934 7 169 1.0 89
element truss 935 56 54 1.0 89
element truss 936 56 48 1.0 89
element truss 937 156 48 1.0 89
element truss 938 70 156 1.0 89
element truss 939 156 73 1.0 89
element truss 940 89 156 1.0 89
element truss 941 164 55 1.0 89
element truss 942 10 7 1.0 89
element truss 943 70 56 1.0 89
element truss 944 164 56 1.0 89
element truss 945 165 164 1.0 89
element truss 946 165 70 1.0 89
element truss 947 184 164 1.0 89
element truss 948 79 70 1.0 89
element truss 949 79 89 1.0 89
element truss 950 189 165 1.0 89
element truss 951 83 165 1.0 89
element truss 952 83 79 1.0 89
element truss 953 80 79 1.0 89
element truss 954 89 180 1.0 91
element truss 955 189 184 1.0 89
element truss 956 204 189 1.0 89
element truss 957 115 80 1.0 89
element truss 958 99 83 1.0 89
element truss 959 99 189 1.0 89
element truss 960 115 83 1.0 89
element truss 961 136 115 1.0 89
element truss 962 121 115 1.0 89
element truss 963 200 99 1.0 89
element truss 964 88 157 1.0 91
element truss 965 121 99 1.0 89
element truss 966 200 204 1.0 89
element truss 967 118 136 1.0 89
element truss 968 129 121 1.0 89
element truss 969 118 121 1.0 89
element truss 970 129 200 1.0 89
element truss 971 202 200 1.0 89
element truss 972 32 179 1.0 91
element truss 973 93 89 1.0 91
element truss 974 180 72 1.0 87
element truss 975 184 65 1.0 93
element truss 976 204 185 1.0 93
element truss 977 185 184 1.0 93
element truss 978 55 64 1.0 93
element truss 979 65 55 1.0 93
element truss 980 115 53 1.0 97
element truss 981 135 115 1.0 97
element truss 982 53 79 1.0 97
element truss 983 79 74 1.0 97
element truss 984 74 156 1.0 97
element truss 985 50 163 1.0 89
element truss 986 57 163 1.0 89
element truss 987 50 49 1.0 89
element truss 988 35 31 1.0 89
element truss 989 35 61 1.0 89
element truss 990 74 50 1.0 89
element truss 991 157 49 1.0 89
element truss 992 74 157 1.0 89
element truss 993 63 50 1.0 89
element truss 994 65 57 1.0 89
element truss 995 63 57 1.0 89
element truss 996 62 63 1.0 89
element truss 997 62 65 1.0 89
element truss 998 53 75 1.0 89
element truss 999 52 74 1.0 89
element truss 1000 75 74 1.0 89
element truss 1001 52 63 1.0 89
element truss 1002 178 52 1.0 89
element truss 1003 53 52 1.0 89
element truss 1004 106 178 1.0 89
element truss 1005 106 185 1.0 89
element truss 1006 185 62 1.0 89
element truss 1007 178 62 1.0 89
element truss 1008 105 53 1.0 89
element truss 1009 105 178 1.0 89
element truss 1010 135 112 1.0 89
element truss 1011 112 53 1.0 89
element truss 1012 135 105 1.0 89
element truss 1013 122 106 1.0 89
element truss 1014 122 105 1.0 89
element truss 1015 198 106 1.0 89
element truss 1016 117 122 1.0 89
element truss 1017 201 198 1.0 89
element truss 1018 201 122 1.0 89
element truss 1019 117 135 1.0 89
element truss 1020 138 135 1.0 89
element truss 1021 198 204 1.0 93

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 47), with Mesh Node = 48 (auxiliary for element 1022)
node 1671 8000 5500 4600
rigidLink beam 48 1671
# Geometric transformation command
geomTransf PDelta 1022 1.0 0.0 -0.0
element forceBeamColumn 1022 214 1671 1022 HingeRadau 6 200.0 6 200.0 7


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 47), with Mesh Node = 48 (auxiliary for element 1023)
node 1672 8200 5500 4800
rigidLink beam 225 1672


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 168), with Mesh Node = 169 (auxiliary for element 1023)
node 1673 11800 5500 4800
rigidLink beam 335 1673

# Extra nodes for zeroLength
# node tag x y z
node 1674 8200 5500 4800
node 1675 11800 5500 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 1023 0.0 0.0 1.0
element elasticBeamColumn 1023 1674 1675 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 1023

# zero_length_elements zeroLength
element zeroLength 1968 1672 1674 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1969 1675 1673 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 168), with Mesh Node = 169 (auxiliary for element 1024)
node 1676 12000 5700 4800
rigidLink beam 335 1676


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 162), with Mesh Node = 163 (auxiliary for element 1024)
node 1677 12000 8800 4800
rigidLink beam 329 1677

# Extra nodes for zeroLength
# node tag x y z
node 1678 12000 5700 4800
node 1679 12000 8800 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 1024 0.0 -0.0 1.0
element elasticBeamColumn 1024 1678 1679 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 1024

# zero_length_elements zeroLength
element zeroLength 1970 1676 1678 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0
element zeroLength 1971 1679 1677 -mat 5 5 5 5 57 5 -dir 1 2 3 4 5 6 -orient 0.0 1.0 0.0 -1.0 0.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 168), with Mesh Node = 169 (auxiliary for element 1025)
node 1680 12000 5500 4600
rigidLink beam 169 1680
# Geometric transformation command
geomTransf PDelta 1025 1.0 0.0 -0.0
element forceBeamColumn 1025 215 1680 1025 HingeRadau 6 200.0 6 200.0 7


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 168), with Mesh Node = 169 (auxiliary for element 1026)
node 1681 12000 5500 5000
rigidLink beam 169 1681


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 55), with Mesh Node = 56 (auxiliary for element 1026)
node 1682 12000 5500 7900
rigidLink beam 56 1682
# Geometric transformation command
geomTransf PDelta 1026 1.0 0.0 -0.0
element forceBeamColumn 1026 1681 1682 1026 HingeRadau 8 200.0 8 200.0 9


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 168), with Mesh Node = 169 (auxiliary for element 1027)
node 1683 12200 5500 4800
rigidLink beam 335 1683


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 53), with Mesh Node = 54 (auxiliary for element 1027)
node 1684 15800 5500 4800
rigidLink beam 231 1684

# Extra nodes for zeroLength
# node tag x y z
node 1685 12200 5500 4800
node 1686 15800 5500 4800

# beam_column_elements elasticBeamColumn
# Geometric transformation command
geomTransf Linear 1027 0.0 0.0 1.0
element elasticBeamColumn 1027 1685 1686 120000.0 25000.0 15000.0 1943850585.9374998 560000000.0 315000000.0 1027

# zero_length_elements zeroLength
element zeroLength 1972 1683 1685 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0
element zeroLength 1973 1686 1684 -mat 5 5 5 5 28 5 -dir 1 2 3 4 5 6 -orient 1.0 0.0 0.0 0.0 1.0 0.0

# beam_column_elements forceBeamColumn


# RCJointModel3D at Geometry = 1784 (Sub-Vertex = 162), with Mesh Node = 163 (auxiliary for element 1028)
node 1687 12000 9000 4600
rigidLink beam 163 1687
# Geometric transformation command
geomTransf PDelta 1028 1.0 0.0 -0.0
element forceBeamColumn 1028 216 1687 1028 HingeRadau 6 200.0 6 200.0 7
