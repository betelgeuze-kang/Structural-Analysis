use std::fmt::Write as _;

use structural_contracts::product_ir::{
    sha256_identity, NonlinearNdthaResultIrV1, NonlinearNdthaTerminalStatusV1,
};

use crate::WorkbenchError;

pub(crate) const RESPONSE_VIEW_SCHEMA_V1: &str =
    "structural-native-workbench-ndtha-response-view.v1";
pub const WORKBENCH_RESULT_VIEW_DEFAULT_COUNT_V1: u32 = 64;
pub const WORKBENCH_RESULT_VIEW_MAX_COUNT_V1: u32 = 256;
const PLOT_WIDTH: usize = 41;

/// Closed response-channel vocabulary for the bounded NDTHA result explorer.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum WorkbenchResultChannelV1 {
    TopDisplacement,
    DriftRatio,
    BaseShear,
    ResidualInf,
}

struct ResponseWindow<'a> {
    values: &'a [f64],
    completed: usize,
    start: usize,
    end: usize,
    minimum: f64,
    maximum: f64,
}

impl WorkbenchResultChannelV1 {
    #[must_use]
    pub const fn label(self) -> &'static str {
        match self {
            Self::TopDisplacement => "top-displacement",
            Self::DriftRatio => "drift-ratio",
            Self::BaseShear => "base-shear",
            Self::ResidualInf => "residual-inf",
        }
    }

    #[must_use]
    pub fn parse(value: &str) -> Option<Self> {
        match value {
            "top-displacement" => Some(Self::TopDisplacement),
            "drift-ratio" => Some(Self::DriftRatio),
            "base-shear" => Some(Self::BaseShear),
            "residual-inf" => Some(Self::ResidualInf),
            _ => None,
        }
    }

    const fn unit(self) -> &'static str {
        match self {
            Self::TopDisplacement => "m",
            Self::DriftRatio => "percent",
            Self::BaseShear => "kN",
            Self::ResidualInf => "N",
        }
    }

    fn values(self, result: &NonlinearNdthaResultIrV1) -> &[f64] {
        match self {
            Self::TopDisplacement => &result.response.top_displacement_m,
            Self::DriftRatio => &result.response.drift_ratio_pct,
            Self::BaseShear => &result.response.base_shear_kn,
            Self::ResidualInf => &result.response.step_residual_inf,
        }
    }
}

/// Render one deterministic, bounded window over a strictly verified terminal `ResultIR`.
pub(crate) fn render_ndtha_response_view(
    result: &NonlinearNdthaResultIrV1,
    channel: WorkbenchResultChannelV1,
    start_step: u32,
    count: u32,
) -> Result<String, WorkbenchError> {
    let window = response_window(result, channel, start_step, count)?;
    let terminal_status = match result.summary.terminal_status {
        NonlinearNdthaTerminalStatusV1::Completed => "completed",
        NonlinearNdthaTerminalStatusV1::Collapsed => "collapsed",
    };
    let mut output = String::new();
    push_response_header(&mut output, result, channel, &window, terminal_status);
    push_response_rows(&mut output, result, &window);
    push_line(&mut output, "");
    push_line(
        &mut output,
        "Boundary: bounded terminal view of one verified NDTHA ResultIR response channel; not a time reconstruction, 3D/deformed/modal/contour view, engineering acceptance, or design-code compliance.",
    );
    let view_hash = sha256_identity(output.as_bytes());
    push_field(&mut output, "View hash", &view_hash);
    if output.as_bytes().contains(&0x1b) {
        return Err(WorkbenchError::new(
            "workbench_result_view_unsafe",
            "response view unexpectedly contains an escape byte",
        ));
    }
    Ok(output)
}

fn response_window(
    result: &NonlinearNdthaResultIrV1,
    channel: WorkbenchResultChannelV1,
    start_step: u32,
    count: u32,
) -> Result<ResponseWindow<'_>, WorkbenchError> {
    if start_step == 0 || count == 0 || count > WORKBENCH_RESULT_VIEW_MAX_COUNT_V1 {
        return Err(window_error(format!(
            "start step must be at least 1 and count must be in 1..={WORKBENCH_RESULT_VIEW_MAX_COUNT_V1}"
        )));
    }
    let completed = usize::try_from(result.summary.step_count_completed).map_err(|_| {
        WorkbenchError::new(
            "workbench_result_view_result_invalid",
            "completed step count does not fit the native address space",
        )
    })?;
    let start = usize::try_from(start_step - 1)
        .map_err(|_| window_error("start step does not fit the native address space".to_owned()))?;
    if start >= completed {
        return Err(window_error(format!(
            "start step {start_step} exceeds the {completed} completed response steps"
        )));
    }
    let requested_count = usize::try_from(count)
        .map_err(|_| window_error("count does not fit the native address space".to_owned()))?;
    let end = start.saturating_add(requested_count).min(completed);
    let values = channel.values(result);
    if values.len() < completed
        || result.response.step_converged.len() < completed
        || result.response.step_iterations.len() < completed
        || result.response.step_plastic_story_count.len() < completed
        || result.response.step_residual_inf.len() < completed
    {
        return Err(WorkbenchError::new(
            "workbench_result_view_result_invalid",
            "verified ResultIR response vectors do not cover the completed prefix",
        ));
    }
    let (minimum, maximum) = extent(&values[..completed]).ok_or_else(|| {
        WorkbenchError::new(
            "workbench_result_view_result_invalid",
            "verified ResultIR has no completed response values",
        )
    })?;
    Ok(ResponseWindow {
        values,
        completed,
        start,
        end,
        minimum,
        maximum,
    })
}

fn push_response_header(
    output: &mut String,
    result: &NonlinearNdthaResultIrV1,
    channel: WorkbenchResultChannelV1,
    window: &ResponseWindow<'_>,
    terminal_status: &str,
) {
    push_line(
        output,
        "Structural Native Workbench - NDTHA response history",
    );
    push_field(output, "Schema", RESPONSE_VIEW_SCHEMA_V1);
    push_field(output, "Case", &result.case_id);
    push_field(output, "Authority", "bounded candidate");
    push_field(output, "Terminal status", terminal_status);
    push_field(output, "Channel", channel.label());
    push_field(output, "Unit", channel.unit());
    push_field(output, "Completed steps", &window.completed.to_string());
    push_field(
        output,
        "Displayed steps",
        &format!(
            "{}-{} of {}",
            window.start + 1,
            window.end,
            window.completed
        ),
    );
    push_field(output, "Minimum", &format!("{:+.17e}", window.minimum));
    push_field(output, "Maximum", &format!("{:+.17e}", window.maximum));
    push_field(
        output,
        "Terminal value",
        &format!("{:+.17e}", window.values[window.completed - 1]),
    );
    push_field(output, "Backend", "cpu / fp64 / fallback 0");
    push_field(output, "Result hash", &result.result_hash);
    push_field(output, "Request hash", &result.identity.request_hash);
    push_field(output, "Model hash", &result.identity.model_hash);
    push_field(output, "State hash", &result.identity.state_hash);
    push_field(output, "Execution hash", &result.identity.execution_hash);
    push_field(output, "Checkpoint hash", &result.identity.checkpoint_hash);
    push_line(
        output,
        "Presentation: ASCII fixed-width plot normalized to the selected channel's complete executed extent.",
    );
    push_line(
        output,
        "Horizontal coordinate: one-based step index; ResultIR v1 does not carry dt_s, so no time value is inferred.",
    );
    push_line(output, "");
    push_line(
        output,
        "Step   Plot                                      Value                  Conv Iter       Plastic Residual inf (N)",
    );
}

fn push_response_rows(
    output: &mut String,
    result: &NonlinearNdthaResultIrV1,
    window: &ResponseWindow<'_>,
) {
    for (offset, &value) in window.values[window.start..window.end].iter().enumerate() {
        let index = window.start + offset;
        let plot = plot_value(value, window.minimum, window.maximum);
        let converged = if result.response.step_converged[index] {
            "yes"
        } else {
            "no "
        };
        writeln!(
            output,
            "{:06} [{}] {:+.17e} {}  {:010} {:07} {:+.17e}",
            index + 1,
            plot,
            value,
            converged,
            result.response.step_iterations[index],
            result.response.step_plastic_story_count[index],
            result.response.step_residual_inf[index],
        )
        .expect("writing to a String cannot fail");
    }
}

fn window_error(detail: String) -> WorkbenchError {
    WorkbenchError::new("workbench_result_view_window_invalid", detail)
}

fn extent(values: &[f64]) -> Option<(f64, f64)> {
    let (&first, rest) = values.split_first()?;
    let mut minimum = first;
    let mut maximum = first;
    for &value in rest {
        minimum = minimum.min(value);
        maximum = maximum.max(value);
    }
    Some((minimum, maximum))
}

fn plot_value(value: f64, minimum: f64, maximum: f64) -> String {
    let mut plot = [' '; PLOT_WIDTH];
    if minimum <= 0.0 && maximum >= 0.0 {
        plot[plot_position(0.0, minimum, maximum)] = '|';
    }
    plot[plot_position(value, minimum, maximum)] = '*';
    plot.into_iter().collect()
}

fn plot_position(value: f64, minimum: f64, maximum: f64) -> usize {
    if minimum
        .partial_cmp(&maximum)
        .is_some_and(std::cmp::Ordering::is_eq)
    {
        return PLOT_WIDTH / 2;
    }
    let fraction = if minimum < 0.0 && maximum > 0.0 {
        (value * 0.5 - minimum * 0.5) / (maximum * 0.5 - minimum * 0.5)
    } else {
        (value - minimum) / (maximum - minimum)
    };
    let scaled = fraction.clamp(0.0, 1.0) * 40.0;
    let mut position = 0;
    for candidate in 1..PLOT_WIDTH {
        let candidate_u32 = u32::try_from(candidate).expect("plot width fits u32");
        if scaled < f64::from(candidate_u32) - 0.5 {
            break;
        }
        position = candidate;
    }
    position
}

fn push_line(output: &mut String, value: &str) {
    output.push_str(value);
    output.push('\n');
}

fn push_field(output: &mut String, label: &str, value: &str) {
    output.push_str(label);
    output.push_str(": ");
    push_line(output, value);
}

#[cfg(test)]
mod tests {
    use super::{extent, plot_position, plot_value, PLOT_WIDTH};

    #[test]
    fn plot_uses_fixed_endpoints_and_a_visible_zero_axis() {
        assert_eq!(plot_position(-2.0, -2.0, 2.0), 0);
        assert_eq!(plot_position(0.0, -2.0, 2.0), PLOT_WIDTH / 2);
        assert_eq!(plot_position(2.0, -2.0, 2.0), PLOT_WIDTH - 1);
        let negative = plot_value(-2.0, -2.0, 2.0);
        assert_eq!(negative.len(), PLOT_WIDTH);
        assert_eq!(negative.as_bytes()[0], b'*');
        assert_eq!(negative.as_bytes()[PLOT_WIDTH / 2], b'|');
    }

    #[test]
    fn constant_and_extreme_extents_remain_bounded() {
        assert_eq!(plot_position(3.0, 3.0, 3.0), PLOT_WIDTH / 2);
        assert_eq!(plot_position(-f64::MAX, -f64::MAX, f64::MAX), 0);
        assert_eq!(plot_position(f64::MAX, -f64::MAX, f64::MAX), PLOT_WIDTH - 1);
        assert_eq!(extent(&[2.0, -1.0, 3.0]), Some((-1.0, 3.0)));
        assert_eq!(extent(&[]), None);
    }
}
