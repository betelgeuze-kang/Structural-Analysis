//! Report projection ownership boundary.

#![forbid(unsafe_code)]

/// Foundation report identity. ResultIR/ReportIR projection is introduced later.
#[must_use]
pub const fn report_contract_version() -> &'static str {
    "report-ir.foundation.v1"
}

#[cfg(test)]
mod tests {
    use super::report_contract_version;

    #[test]
    fn foundation_does_not_claim_an_engineering_report() {
        assert_eq!(report_contract_version(), "report-ir.foundation.v1");
    }
}
