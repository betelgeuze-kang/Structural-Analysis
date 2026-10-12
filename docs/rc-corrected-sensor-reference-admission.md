# Corrected sensor CSV reference admission

`compile_corrected_sensor_reference` compiles every data record of one frozen
corrected sensor CSV into the native ordinal-history plan. The caller supplies
the complete SHA-256, complete record count, source/specimen identifier, three
channel names and explicit signs. Inches convert to meters and kip to kN using
fixed factors. No zero correction, fitting, averaging, downsampling or prefix
selection is performed. Repeated records remain separate observations.

The complete original bytes, all metadata and every data cell are bound by
hashes. Each plan row preserves its zero-based CSV record index and its original
ordinal. The selected measured force remains a separate observation; it is not
used to pick a displacement sign, force sign, material parameter or load factor.
Non-selected sensor columns remain in the original file and in each row hash.

This profile treats `Time` as an ordinal only, even when the metadata unit says
`hh:mm:ss`. It establishes no seconds, strain rate, dynamic loading or physical
clock. It admits corrected source records, not original DAQ channels. In
particular, selecting `N_Face` does not identify an author's support/stub
correction formula or demonstrate equivalence to a modeled drift observation.

The source read is limited to a regular CSV file of at most 8 MiB with at most
65,536 observations and 64 columns. Symlinks, nonregular inputs, environment
files, checksum/count changes, missing/reordered ordinals, incompatible channel
types/units and nonfinite selected values are refused before returning a plan.
No solver, worker, source download or original-file write is performed.

Compilation alone does not admit geometry, boundary conditions, force-pattern
meaning, initial/preloaded material state or a complete constitutive law.
Those remain explicit, separately reviewed inputs to any numerical execution.
It is also not a public job/workbench admission or an independent physical
validation result.
