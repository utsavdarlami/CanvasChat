## **Python Coding Guidelines — Anti-Patterns, Code Smells, and Refactoring Practices**

### **1. General Principles**

*   **Readable First:** Code should be easy to read and understand, as maintainability is critical. External readers (and your future self) should not struggle to infer intent.
*   **Single Responsibility:** Each unit (function/class/module) should do *one thing well*. Avoid bundling unrelated logic.
*   **Minimize Nesting:** Avoid deep nesting of conditions or loops; prefer early exits and small helper functions to reduce cognitive load.

---

### **2. Anti-Patterns and Code Smells to Avoid**

#### **2.1 Structural and Design Anti-Patterns**

*   **God Class (Large Class):** A class that does too much should be refactored into smaller, cohesive classes, each with a focused responsibility.
*   **Shotgun Surgery:** If a single change affects many disparate locations in the codebase, it likely indicates poor cohesion. Refactor to isolate responsibilities.
*   **Spaghetti Code:** Unstructured, tangled logic that makes understanding and maintaining code difficult. Break it into functions or classes with clear flows.
*   **Duplicate Code:** Repeated logic should be extracted into functions, classes, or utilities to adhere to *DRY* principles.
*   **Long Parameter Lists:** A function with many arguments is hard to use and maintain. Group related parameters or encapsulate them in objects.

#### **2.2 Code Smells in Logic and Style**

*   **Magic Numbers/Strings:** Replace hard-coded literals with named constants to improve meaning and maintainability.
*   **Nested Callbacks/Deep Nesting:** Reduce complex indented blocks; use early returns and modularization to flatten control flow.
*   **Obscure Logic:** Avoid overly complex expressions or nested logic that obscures intent; split into intermediate variables or helper functions.

---

### **3. Parameters and Error Handling**

*   **No Unused Parameters:** Functions and methods should not include parameters that are never referenced. If a parameter is required by an interface but unused in implementation, document why or use `_` as the name to signal intentional omission.
*   **Minimal and Clear Error Handling:**

    *   Avoid broad or unnecessary `try/except` blocks that catch exceptions without actionable handling.
    *   Only catch exceptions you can meaningfully handle (e.g., cleaning up, producing a helpful message, or raising a more specific error).
    *   Let exceptions propagate when the caller is better suited to handle them, especially in library code.

---

### **4. Refactoring Strategies**

#### **4.1 Make Code Intent Explicit**

*   Use **meaningful names** for variables, functions, classes, and constants.
*   Add **docstrings** to modules, classes, and functions to clarify purpose and expected behavior.

#### **4.2 Break Down Large Units**

*   Refactor large functions or classes that perform multiple tasks into smaller, testable units.
*   Helpers should have descriptive names that convey their logic to reduce nesting and complexity.

#### **4.3 Simplify Control Flow**

*   Prefer *guard clauses* and early returns to avoid nested logic structures.
*   Avoid redundant conditions and combine related checks to flatten code structure.

---

### **5. Maintainable and Testable Code**

*   **Write Testable Units:** Smaller functions and classes are easier to test. Avoid coupling logic and side effects that complicate testing.
*   **Documentation and Comments:** Comments should clarify *why* something is done when intent isn’t obvious; prefer self-documenting code.
*   **Adopt Static Analysis:** Use tools like *linting*, *type checking*, and *smell detection* to proactively identify issues.

---

### **6. Example Refactoring Checklist**

Before merging changes, evaluate code against this checklist:

*   Do functions and methods have precise, necessary parameters only?
*   Are there any unused parameters or variables?
*   Is error handling specific and purposeful?
*   Are magic numbers replaced with constants?
*   Is logic free of deep nesting and spaghetti patterns?
*   Has duplicated code been consolidated?
*   Are classes following single responsibility?
*   Are docstrings present and informative?

---

These guidelines combine traditional software engineering practices for readable, maintainable Python code with your specific rules on parameter usage and error handling. They serve as both a **coding standard** and a **refactoring guide** to elevate codebase quality systematically.
