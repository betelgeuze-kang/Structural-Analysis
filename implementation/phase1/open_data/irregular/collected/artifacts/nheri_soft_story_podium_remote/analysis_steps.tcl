
# Statistics monitor actor
set MonitorActorStatistics_once_flag 0
proc MonitorActorStatistics {} {
	global STKO_VAR_process_id
	global STKO_VAR_increment
	global STKO_VAR_time_increment
	global STKO_VAR_time
	global STKO_VAR_num_iter
	global STKO_VAR_error_norm
	global STKO_VAR_percentage
	global MonitorActorStatistics_once_flag
	# Statistics
	if {$STKO_VAR_process_id == 0} {
		if {$MonitorActorStatistics_once_flag == 0} {
			set MonitorActorStatistics_once_flag 1
			set STKO_monitor_statistics [open "./STKO_monitor_statistics.stats"  w+]
		} else {
			set STKO_monitor_statistics [open "./STKO_monitor_statistics.stats"  a+]
		}
		puts $STKO_monitor_statistics "$STKO_VAR_increment $STKO_VAR_time_increment $STKO_VAR_time $STKO_VAR_num_iter $STKO_VAR_error_norm $STKO_VAR_percentage"
		close $STKO_monitor_statistics
	}
}
lappend STKO_VAR_MonitorFunctions "MonitorActorStatistics"

# Timing monitor actor
set monitor_actor_time_0 [clock seconds]
proc MonitorActorTiming {} {
	global monitor_actor_time_0
	global STKO_VAR_process_id
	if {$STKO_VAR_process_id == 0} {
		set STKO_time [open "./STKO_time_monitor.tim" w+]
		set current_time [clock seconds]
		puts $STKO_time $monitor_actor_time_0
		puts $STKO_time $current_time
		close $STKO_time
	}
}
lappend STKO_VAR_MonitorFunctions "MonitorActorTiming"

#TCL script: parameter declaration
# Note: in OpenSeesMP the processor ID is in the range [0, N[

# declare the current parameter ID
set param_id [getPID]

# declare the parametrized recorder file name
set mpco_fname "Results_$param_id"

# this is a trick... when STKO writes the mpco recorder command, it also writes
# a support *.mpco.cdata file with the same name of the recorder. However in STKO the 
# recorder name has a suffix = $param_id, that will be evaluated by TCL when creating the
# *.mpco file, but not at the time STKO writes the *.mpco.cdata file. So we can
# simply copy the one created by STKO and rename it accordingly.
# this is the name STKO gave it... make sure to use the escape character before the $ char!!
set STKO_file_name "\$mpco_fname.mpco.cdata"
# this is the new name, DON'T use the escape character, to the param_id will be eval by TCL!
set current_file_name "$mpco_fname.mpco.cdata"
file copy -force $STKO_file_name $current_file_name

# directories for ground motion files
# read their content, split every line, skip empty lines
set gmotion_dt [lsearch -all -inline -not -exact [split [read [open "GroundMotionInfo/GMTimeSteps.txt" r]] "\n"] {}]
set gmotion_nsteps [lsearch -all -inline -not -exact [split [read [open "GroundMotionInfo/GMNumPoints.txt" r]] "\n"] {}]
set gmotion_names [lsearch -all -inline -not -exact [split [read [open "GroundMotionInfo/GMFileNames.txt" r]] "\n"] {}]

# make sure they have the same length
set num_dt [llength $gmotion_dt]
set num_nsteps [llength $gmotion_nsteps]
set num_names [llength $gmotion_names]
if {$num_dt != $num_nsteps || $num_dt != $num_names} {
	puts $num_dt
	puts $num_nsteps
	puts $num_names
	error "The GroundMotionInfo files must have the same length"
}

# make sure the user input a correct number of processors
set num_proc [getNP]
set num_param [expr int($num_dt/2)]
if {$num_proc != $num_param} {
	error "The number of processors ($num_proc) must be equal to the number of parameters ($num_param)"
}

# ground motion come in contiguous pairs, here we get their line (0 based)
set gmotion_x_line [expr $param_id*2]
set gmotion_y_line [expr $param_id*2 + 1]

# ground motion x data
set gmotion_x_dt [lindex $gmotion_dt $gmotion_x_line]
set gmotion_x_nsteps [lindex $gmotion_nsteps $gmotion_x_line]
set gmotion_x_file "histories/[lindex $gmotion_names $gmotion_x_line].txt"

# ground motion y data
set gmotion_y_dt [lindex $gmotion_dt $gmotion_y_line]
set gmotion_y_nsteps [lindex $gmotion_nsteps $gmotion_y_line]
set gmotion_y_file "histories/[lindex $gmotion_names $gmotion_y_line].txt"

# since these 2 ground motion are applied in the same analysis,
# we need to make sure the dt and total duration are compatible
set gmotion_x_duration [expr $gmotion_x_dt * $gmotion_x_nsteps]
set gmotion_y_duration [expr $gmotion_y_dt * $gmotion_y_nsteps]
set gmotion_duration [expr max($gmotion_x_duration, $gmotion_y_duration)]
set gmotion_dt [expr min($gmotion_x_dt, $gmotion_y_dt)]
set gmotion_num_steps [expr max(1, int($gmotion_duration / $gmotion_dt))]
set gmotion_dt [expr $gmotion_duration/$gmotion_num_steps]

# print some info... wait 1 second just to make sure every proc reached this point
# this piece of code is not necessary, just to print some info in a clear way
barrier
after 1000 set end 1
vwait end
puts "\nProcessor: $param_id:\n\
   GMX: '$gmotion_x_file' - dt: $gmotion_x_dt - #steps: $gmotion_x_nsteps\n\
   GMY: '$gmotion_y_file' - dt: $gmotion_y_dt - #steps: $gmotion_y_nsteps"
barrier
after 1000 set end 1
vwait end

recorder mpco "$mpco_fname.mpco" \
-N "displacement" "rotation" "velocity" "acceleration" "reactionForce" "reactionMoment" \
-T nsteps 50 \
-E "force" "deformation" "localForce" "damage" "section.force" "section.deformation" "material.stress" "material.strain" "section.fiber.stress" "section.fiber.strain" "section.fiber.damage"

# Constraints.sp fix
	fix 142 1 1 1 1 1 1
	fix 143 1 1 1 1 1 1
	fix 144 1 1 1 1 1 1
	fix 145 1 1 1 1 1 1
	fix 146 1 1 1 1 1 1
	fix 147 1 1 1 1 1 1
	fix 148 1 1 1 1 1 1
	fix 149 1 1 1 1 1 1
	fix 150 1 1 1 1 1 1
	fix 151 1 1 1 1 1 1
	fix 152 1 1 1 1 1 1
	fix 194 1 1 1 1 1 1
	fix 205 1 1 1 1 1 1
	fix 206 1 1 1 1 1 1
	fix 207 1 1 1 1 1 1
	fix 208 1 1 1 1 1 1
	fix 209 1 1 1 1 1 1
	fix 210 1 1 1 1 1 1
	fix 211 1 1 1 1 1 1
	fix 212 1 1 1 1 1 1
	fix 213 1 1 1 1 1 1
	fix 214 1 1 1 1 1 1
	fix 215 1 1 1 1 1 1
	fix 216 1 1 1 1 1 1
	fix 224 0 0 1 1 1 0
	fix 217 0 0 1 1 1 0
	fix 218 0 0 1 1 1 0
	fix 219 0 0 1 1 1 0
	fix 220 0 0 1 1 1 0
	fix 221 0 0 1 1 1 0
	fix 222 0 0 1 1 1 0
	fix 223 0 0 1 1 1 0

# Constraints.mp rigidDiaphragm
rigidDiaphragm 3 218 1
rigidDiaphragm 3 217 2
rigidDiaphragm 3 218 3
rigidDiaphragm 3 219 4
rigidDiaphragm 3 218 5
rigidDiaphragm 3 219 6
rigidDiaphragm 3 218 7
rigidDiaphragm 3 220 8
rigidDiaphragm 3 220 9
rigidDiaphragm 3 219 10
rigidDiaphragm 3 220 11
rigidDiaphragm 3 221 12
rigidDiaphragm 3 221 13
rigidDiaphragm 3 222 14
rigidDiaphragm 3 221 15
rigidDiaphragm 3 219 16
rigidDiaphragm 3 222 17
rigidDiaphragm 3 222 18
rigidDiaphragm 3 223 19
rigidDiaphragm 3 223 20
rigidDiaphragm 3 223 21
rigidDiaphragm 3 224 22
rigidDiaphragm 3 224 23
rigidDiaphragm 3 224 24
rigidDiaphragm 3 220 25
rigidDiaphragm 3 222 26
rigidDiaphragm 3 218 27
rigidDiaphragm 3 217 28
rigidDiaphragm 3 222 29
rigidDiaphragm 3 220 30
rigidDiaphragm 3 217 31
rigidDiaphragm 3 219 32
rigidDiaphragm 3 219 33
rigidDiaphragm 3 217 34
rigidDiaphragm 3 218 35
rigidDiaphragm 3 219 36
rigidDiaphragm 3 220 37
rigidDiaphragm 3 221 38
rigidDiaphragm 3 221 39
rigidDiaphragm 3 221 40
rigidDiaphragm 3 222 41
rigidDiaphragm 3 223 42
rigidDiaphragm 3 223 43
rigidDiaphragm 3 223 44
rigidDiaphragm 3 224 45
rigidDiaphragm 3 224 46
rigidDiaphragm 3 224 47
rigidDiaphragm 3 217 48
rigidDiaphragm 3 217 49
rigidDiaphragm 3 218 50
rigidDiaphragm 3 218 51
rigidDiaphragm 3 220 52
rigidDiaphragm 3 221 53
rigidDiaphragm 3 217 54
rigidDiaphragm 3 218 55
rigidDiaphragm 3 218 56
rigidDiaphragm 3 218 57
rigidDiaphragm 3 218 58
rigidDiaphragm 3 218 59
rigidDiaphragm 3 218 60
rigidDiaphragm 3 217 61
rigidDiaphragm 3 220 62
rigidDiaphragm 3 219 63
rigidDiaphragm 3 217 64
rigidDiaphragm 3 219 65
rigidDiaphragm 3 219 66
rigidDiaphragm 3 219 67
rigidDiaphragm 3 220 68
rigidDiaphragm 3 219 69
rigidDiaphragm 3 219 70
rigidDiaphragm 3 217 71
rigidDiaphragm 3 217 72
rigidDiaphragm 3 217 73
rigidDiaphragm 3 219 74
rigidDiaphragm 3 220 75
rigidDiaphragm 3 220 76
rigidDiaphragm 3 217 77
rigidDiaphragm 3 220 78
rigidDiaphragm 3 220 79
rigidDiaphragm 3 221 80
rigidDiaphragm 3 221 81
rigidDiaphragm 3 221 82
rigidDiaphragm 3 221 83
rigidDiaphragm 3 220 84
rigidDiaphragm 3 221 85
rigidDiaphragm 3 221 86
rigidDiaphragm 3 221 87
rigidDiaphragm 3 219 88
rigidDiaphragm 3 219 89
rigidDiaphragm 3 219 90
rigidDiaphragm 3 217 91
rigidDiaphragm 3 221 92
rigidDiaphragm 3 220 93
rigidDiaphragm 3 222 94
rigidDiaphragm 3 223 95
rigidDiaphragm 3 222 96
rigidDiaphragm 3 222 97
rigidDiaphragm 3 222 98
rigidDiaphragm 3 222 99
rigidDiaphragm 3 222 100
rigidDiaphragm 3 222 101
rigidDiaphragm 3 222 102
rigidDiaphragm 3 222 103
rigidDiaphragm 3 223 104
rigidDiaphragm 3 222 105
rigidDiaphragm 3 222 106
rigidDiaphragm 3 223 107
rigidDiaphragm 3 223 108
rigidDiaphragm 3 223 109
rigidDiaphragm 3 223 110
rigidDiaphragm 3 222 111
rigidDiaphragm 3 222 112
rigidDiaphragm 3 222 113
rigidDiaphragm 3 222 114
rigidDiaphragm 3 222 115
rigidDiaphragm 3 224 116
rigidDiaphragm 3 224 117
rigidDiaphragm 3 224 118
rigidDiaphragm 3 223 119
rigidDiaphragm 3 223 120
rigidDiaphragm 3 223 121
rigidDiaphragm 3 223 122
rigidDiaphragm 3 222 123
rigidDiaphragm 3 224 124
rigidDiaphragm 3 224 125
rigidDiaphragm 3 221 126
rigidDiaphragm 3 223 127
rigidDiaphragm 3 224 128
rigidDiaphragm 3 224 129
rigidDiaphragm 3 223 130
rigidDiaphragm 3 224 131
rigidDiaphragm 3 224 132
rigidDiaphragm 3 224 133
rigidDiaphragm 3 224 134
rigidDiaphragm 3 223 135
rigidDiaphragm 3 223 136
rigidDiaphragm 3 223 137
rigidDiaphragm 3 224 138
rigidDiaphragm 3 224 139
rigidDiaphragm 3 224 140
rigidDiaphragm 3 224 141
rigidDiaphragm 3 218 153
rigidDiaphragm 3 218 154
rigidDiaphragm 3 218 155
rigidDiaphragm 3 218 156
rigidDiaphragm 3 218 157
rigidDiaphragm 3 219 158
rigidDiaphragm 3 220 159
rigidDiaphragm 3 219 160
rigidDiaphragm 3 219 161
rigidDiaphragm 3 219 162
rigidDiaphragm 3 217 163
rigidDiaphragm 3 219 164
rigidDiaphragm 3 220 165
rigidDiaphragm 3 219 166
rigidDiaphragm 3 217 167
rigidDiaphragm 3 217 168
rigidDiaphragm 3 217 169
rigidDiaphragm 3 217 170
rigidDiaphragm 3 217 171
rigidDiaphragm 3 218 172
rigidDiaphragm 3 220 173
rigidDiaphragm 3 217 174
rigidDiaphragm 3 219 175
rigidDiaphragm 3 217 176
rigidDiaphragm 3 220 177
rigidDiaphragm 3 221 178
rigidDiaphragm 3 218 179
rigidDiaphragm 3 218 180
rigidDiaphragm 3 217 181
rigidDiaphragm 3 218 182
rigidDiaphragm 3 220 183
rigidDiaphragm 3 220 184
rigidDiaphragm 3 221 185
rigidDiaphragm 3 220 186
rigidDiaphragm 3 220 187
rigidDiaphragm 3 220 188
rigidDiaphragm 3 221 189
rigidDiaphragm 3 221 190
rigidDiaphragm 3 221 191
rigidDiaphragm 3 221 192
rigidDiaphragm 3 221 193
rigidDiaphragm 3 221 195
rigidDiaphragm 3 217 196
rigidDiaphragm 3 218 197
rigidDiaphragm 3 223 198
rigidDiaphragm 3 223 199
rigidDiaphragm 3 223 200
rigidDiaphragm 3 224 201
rigidDiaphragm 3 224 202
rigidDiaphragm 3 224 203
rigidDiaphragm 3 222 204

# Patterns.addPattern loadPattern
pattern Plain 7 1 {

# Loads.eleLoad eleLoad_beamUniform
eleLoad -ele 81 82 83 85 86 88 95 98 99 100 101 102 105 112 113 114 117 136 137 138 139 141 143 144 146 150 151 152 155 162 164 174 175 176 177 183 186 187 188 189 190 191 194 195 196 197 198 199 200 201 202 203 204 206 209 217 220 223 224 225 227 252 253 254 255 256 258 259 263 264 265 266 267 268 269 270 271 272 273 280 281 285 286 288 289 290 291 292 294 295 318 321 350 356 358 360 368 372 373 374 375 376 377 378 382 383 385 386 387 388 389 390 391 392 394 395 396 398 400 402 403 404 406 410 413 415 424 429 430 431 432 433 435 439 441 444 445 452 457 458 459 460 468 469 470 471 472 474 475 477 480 481 486 493 495 496 499 500 501 502 503 504 505 506 507 508 527 528 529 530 531 536 540 541 542 543 544 545 546 547 548 551 552 553 554 558 560 565 1022 1025 1026 1028 -type -beamUniform 0.0 0.0 -5.0625
eleLoad -ele 133 149 153 154 163 167 169 170 171 172 178 184 185 193 208 236 244 275 279 282 283 284 302 305 310 313 314 317 319 320 324 329 331 335 341 346 347 349 355 357 365 370 371 379 381 384 397 399 405 407 408 409 418 442 443 455 461 462 463 464 466 467 498 510 513 534 535 555 561 563 -type -beamUniform 0.0 -22.166
eleLoad -ele 104 119 129 147 148 179 222 229 261 276 301 316 338 359 414 421 425 427 436 438 440 456 476 482 485 514 550 559 -type -beamUniform 0.0 -23.617
eleLoad -ele 207 212 238 239 248 250 262 488 537 538 -type -beamUniform 0.0 -9.88
eleLoad -ele 241 260 491 494 -type -beamUniform 0.0 -11.27
eleLoad -ele 243 567 -type -beamUniform 0.0 -9.23
eleLoad -ele 205 213 215 240 246 251 487 539 -type -beamUniform 0.0 -18.54
eleLoad -ele 231 247 490 566 -type -beamUniform 0.0 -14.46
eleLoad -ele 192 214 232 237 249 489 492 524 525 526 -type -beamUniform 0.0 -15.68
eleLoad -ele 84 94 96 97 103 106 108 110 116 127 131 132 135 140 142 159 160 161 168 173 210 211 226 242 245 257 274 303 304 306 308 311 315 322 323 336 337 352 366 380 393 401 411 412 419 423 448 449 465 473 478 515 532 533 562 564 -type -beamUniform 0.0 -25.235
eleLoad -ele 93 124 128 180 235 299 339 363 364 422 446 479 509 549 -type -beamUniform 0.0 -21.48
eleLoad -ele 79 90 91 107 109 120 121 130 157 218 219 234 277 297 298 307 309 340 343 354 416 420 453 511 516 517 519 1024 -type -beamUniform 0.0 -20.96
eleLoad -ele 80 87 89 92 111 115 118 122 123 125 126 134 145 156 158 165 166 181 182 216 221 228 230 233 278 287 293 296 300 312 325 326 327 328 330 332 333 334 342 344 345 348 351 353 361 362 367 369 417 426 428 434 437 447 450 451 454 483 484 497 512 518 520 521 522 523 556 557 1023 1027 -type -beamUniform 0.0 -22.16
}

# analyses command
domainChange
constraints Penalty 10000000000000.0 10000000000000.0
numberer RCM
system UmfPack
test NormDispIncr 0.001 10  
algorithm Newton
integrator LoadControl 0.0
analysis Static
# ======================================================================================
# NON-ADAPTIVE LOAD CONTROL ANALYSIS
# ======================================================================================

# ======================================================================================
# USER INPUT DATA 
# ======================================================================================

# duration and initial time step
set total_duration 1.0
set initial_num_incr 10

set STKO_VAR_time 0.0
set STKO_VAR_time_increment [expr $total_duration / $initial_num_incr]
set STKO_VAR_initial_time_increment $STKO_VAR_time_increment
integrator LoadControl $STKO_VAR_time_increment 
for {set STKO_VAR_increment 1} {$STKO_VAR_increment <= $initial_num_incr} {incr STKO_VAR_increment} {
	
	# before analyze
	STKO_CALL_OnBeforeAnalyze
	
	# perform this step
	set STKO_VAR_analyze_done [analyze 1 ]
	
	# update common variables
	if {$STKO_VAR_analyze_done == 0} {
		set STKO_VAR_num_iter [testIter]
		set STKO_VAR_time [expr $STKO_VAR_time + $STKO_VAR_time_increment]
		set STKO_VAR_percentage [expr $STKO_VAR_time/$total_duration]
		set norms [testNorms]
		if {$STKO_VAR_num_iter > 0} {set STKO_VAR_error_norm [lindex $norms [expr $STKO_VAR_num_iter-1]]} else {set STKO_VAR_error_norm 0.0}
	}
	
	# after analyze
	set STKO_VAR_afterAnalyze_done 0
	STKO_CALL_OnAfterAnalyze
	
	# check convergence
	if {$STKO_VAR_analyze_done == 0} {
		# print statistics
		if {$STKO_VAR_process_id == 0} {
			puts [format "Increment: %6d | Iterations: %4d | Norm: %8.3e | Progress: %7.3f %%" $STKO_VAR_increment $STKO_VAR_num_iter  $STKO_VAR_error_norm [expr $STKO_VAR_percentage*100.0]]
		}
	} else {
		# stop analysis
		error "ERROR: the analysis did not converge"
	}
	
}

# done
if {$STKO_VAR_process_id == 0} {
	puts "Target time has been reached. Current time = $STKO_VAR_time"
	puts "SUCCESS."
}

loadConst -time 0.0

wipeAnalysis

#TCL script: excitation x & y (parametrized)
# note: start time series tag at 2, because 1 is used for the Linear time series
set gmotion_x_ts 2
set gmotion_y_ts 3

timeSeries Path $gmotion_x_ts -dt $gmotion_dt -filePath $gmotion_x_file -factor 9810.0
timeSeries Path $gmotion_y_ts -dt $gmotion_dt -filePath $gmotion_y_file -factor 9810.0

pattern UniformExcitation 1 1 -accel $gmotion_x_ts
pattern UniformExcitation 2 2 -accel $gmotion_y_ts

# Misc_commands rayleigh
rayleigh 0.7102092831924128 0.0 0.0024324460200503646 0.0

# Monitor Actor [11]
set nodes_Y_11 {224}
set MonitorActor11_once_flag 0
set last_step_id_previous_stage_X_11 0
set previous_step_id_X_11 1
set previous_monitor_value_X_11 1
proc MonitorActor11 {} {
	global MonitorActor11_once_flag
	global STKO_VAR_process_id
	global STKO_VAR_increment
	if {$MonitorActor11_once_flag == 0} {
		set MonitorActor11_once_flag 1
		set STKO_plot_00 [open "./monitor_[getPID].plt" w+]
		puts $STKO_plot_00 "Time Step ID 	Displacement (X) "
	} else {
		set STKO_plot_00 [open "./monitor_[getPID].plt" a+]
	}
	global last_step_id_previous_stage_X_11
	global previous_step_id_X_11
	global previous_monitor_value_X_11
	if {$STKO_VAR_increment < $previous_step_id_X_11} {
		# It means a new stage has started
		set last_step_id_previous_stage_X_11 $previous_monitor_value_X_11
	}
	set monitor_value_X [expr $STKO_VAR_increment + $last_step_id_previous_stage_X_11]
	set previous_step_id_X_11 $STKO_VAR_increment
	set previous_monitor_value_X_11 $monitor_value_X
	set monitor_value_Y 0.0
	global nodes_Y_11
	foreach node_id $nodes_Y_11 {
		# get node value
		set node_value [nodeDisp $node_id 1]
		set monitor_value_Y [expr $monitor_value_Y + $node_value]
	}
	set monitor_value_Y [expr 1.0 * $monitor_value_Y + 0.0]
	puts $STKO_plot_00 "$monitor_value_X	$monitor_value_Y"
	close $STKO_plot_00
}
lappend STKO_VAR_MonitorFunctions "MonitorActor11"

#TCL script: Drift Recorder (parametrized)
 recorder Drift -file "DriftX_$param_id.txt" -precision 3 \
 -iNode 212 196 197 166 188 195 103 199 \
 -jNode 196 197 166 188 195 103 199 203 \
 -dof 1 -perpDirn 3
 recorder Drift -file "DriftY_$param_id.txt" -precision 3 \
 -iNode 212 196 197 166 188 195 103 199 \
 -jNode 196 197 166 188 195 103 199 203 \
 -dof 2 -perpDirn 3

#TCL script: RECORDER
 recorder Node -file "DISPX_$param_id.txt" -precision 3 \
-time -node 217 218 219 220 221 222 223 224 \
 -dof 1 disp
 recorder Node -file "DISPY_$param_id.txt" -precision 3 \
-time -node 217 218 219 220 221 222 223 224 \
 -dof 2 disp
  recorder Node -file "VelX_$param_id.txt" -precision 3 \
-time -node 217 218 219 220 221 222 223 224 \
 -dof 1 vel
 recorder Node -file "VelY_$param_id.txt" -precision 3 \
-time -node 217 218 219 220 221 222 223 224 \
 -dof 2 vel


#TCL script: acceleration relative
 recorder Node -file "ACCRX_$param_id.txt" -precision 3 \
 -time -node 217 218 219 220 221 222 223 224 \
 -dof 1 accel
 recorder Node -file "ACCRY_$param_id.txt" -precision 3 \
 -time -node 217 218 219 220 221 222 223 224 \
 -dof 2 accel

#TCL script: acceleration absolute
 recorder Node -file "ACCX_$param_id.txt" -precision 3 \
 -timeSeries $gmotion_x_ts  -time -node 217 218 219 220 221 222 223 224 \
 -dof 1 accel
 recorder Node -file "ACCY_$param_id.txt" -precision 3 \
 -timeSeries $gmotion_y_ts  -time -node 217 218 219 220 221 222 223 224 \
 -dof 2 accel


# analyses command
domainChange
constraints Penalty 10000000000000.0 10000000000000.0
numberer RCM
system UmfPack
test NormDispIncr 0.001 100  
algorithm KrylovNewton
integrator Newmark 0.5 0.25
analysis Transient
# Analysis skipped: duration(0.0) * increments(0) = 0


#TCL script: Analysis run (parameterized)
# ======================================================================================
# ADAPTIVE TRANSIENT ANALYSIS
# ======================================================================================

# ======================================================================================
# USER INPUT DATA 
# ======================================================================================

# duration and initial time step
set total_time $gmotion_duration
set initial_num_incr $gmotion_num_steps

# parameters for adaptive time step
set max_factor 1.0
set min_factor 1e-06
set max_factor_increment 1.5
set min_factor_increment 1e-06
set max_iter 200
set desired_iter 100

set increment_counter 0
set factor 1.0
set old_factor $factor
set time 0.0
set initial_time_increment [expr $total_time / $initial_num_incr]
set time_tolerance [expr abs($initial_time_increment) * 1.0e-8]

while 1 {
	
	incr increment_counter
	if {[expr abs($time)] >= [expr abs($total_time)]} {
		if {$STKO_VAR_process_id == 0} {
			puts "Target time has been reached. Current time = $time"
			puts "SUCCESS."
		}
		break
	}
	
	set time_increment [expr $initial_time_increment * $factor]
	if {[expr abs($time + $time_increment)] > [expr abs($total_time) - $time_tolerance]} {
		set time_increment [expr $total_time - $time]
	}
	if {$STKO_VAR_process_id == 0} {
		puts "Increment: $increment_counter. time_increment = $time_increment. Current time = $time"
	}
	
	set ok [analyze 1 $time_increment]
	#barrier
	
	if {$ok == 0} {
		set num_iter [testIter]
		set factor_increment [expr min($max_factor_increment, [expr double($desired_iter) / double($num_iter)])]
		set factor [expr $factor * $factor_increment]
		if {$factor > $max_factor} {
			set factor $max_factor
		}
		if {$STKO_VAR_process_id == 0} {
			if {$factor > $old_factor} {
				puts "Increasing increment factor due to faster convergence. Factor = $factor"
			}
		}
		set old_factor $factor
		set time [expr $time + $time_increment]
		
		# print statistics
		set norms [testNorms]
		if {$num_iter > 0} {set last_norm [lindex $norms [expr $num_iter-1]]} else {set last_norm 0.0}
		if {$STKO_VAR_process_id == 0} {
			puts "Increment: $increment_counter - Iterations: $num_iter - Norm: $last_norm ( [expr $time/$total_time*100.0] % )"
		}
		
		# Call Custom Functions
		set perc [expr $time/$total_time]
		#CustomFunctionCaller $increment_counter $time_increment $time $num_iter $last_norm $perc $STKO_VAR_process_id $is_parallel
		STKO_CALL_OnAfterAnalyze
	} else {
		set num_iter $max_iter
		set factor_increment [expr max($min_factor_increment, [expr double($desired_iter) / double($num_iter)])]
		set factor [expr $factor * $factor_increment]
		if {$STKO_VAR_process_id == 0} {
			puts "Reducing increment factor due to non convergece. Factor = $factor"
		}
		if {$factor < $min_factor} {
			if {$STKO_VAR_process_id == 0} {
				puts "ERROR: current factor is less then the minimum allowed ($factor < $min_factor)"
				puts "Giving up"
			}
			error "ERROR: the analysis did not converge"
		}
	}
	
}

# Done!
puts "ANALYSIS SUCCESSFULLY FINISHED"

# Done!
puts "ANALYSIS SUCCESSFULLY FINISHED"
