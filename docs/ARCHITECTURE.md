# System Architecture

```mermaid
flowchart LR
    A[UI] --> B[Capture]
    A --> C[Alignment]
    A --> D[VMAF Analysis]
    B --> C --> D --> E[Reporting]
```