## ADDED Requirements

### Requirement: AT-SPI2 accessibility tree availability is measured across target applications
The spike SHALL enumerate AT-SPI2-registered applications on the COSMIC desktop and probe 5-10 specific applications for accessibility tree completeness.

#### Scenario: AT-SPI2 bus lists registered applications
- **WHEN** a Python script connects to the session D-Bus `org.a11y.Bus` and introspects `/org/a11y/bus`
- **THEN** the script MUST return a list of accessible application names currently running

#### Scenario: Target application tree is characterized
- **WHEN** the spike probes each target application (COSMIC Edit, COSMIC Terminal, Edge, COSMIC Files, COSMIC Settings, VS Code, one Electron app, others)
- **THEN** for each application, the results MUST record: whether a tree is available, whether button/input name and role are readable, and whether bounding boxes are available

### Requirement: Coverage results inform Phase 2 planning
The spike SHALL produce a summary table quantifying AT-SPI2 coverage to determine how much Phase 2 perception work must rely on visual-only approaches.

#### Scenario: Summary table is produced
- **WHEN** all target applications have been probed
- **THEN** the results MUST include a table with columns: Application, Tree Available (Y/N), Name/Role Readable (Y/N), BBox Available (Y/N)

#### Scenario: Coverage percentage is calculated
- **WHEN** the summary table is complete
- **THEN** the results MUST include a calculated percentage of applications with accessible trees (e.g., "4/8 apps have trees"), informing how much P2 work visual recognition must handle
