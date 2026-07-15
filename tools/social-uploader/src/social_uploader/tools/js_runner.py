"""IIFE return value helper for DrissionPage.run_js.

# ⚠️ This is a compatibility patch for DrissionPage 4.1.x.

## background

DrissionPage's `page.run_js(script)` will internally package scripts that are not recognized as js functions into
    function(){<code>}
Then execute via CDP `Runtime.callFunctionOn`. `is_js_func()` only in
`script.strip().startswith('function')` **and** `endswith('}')` are not packaged.

For scripts in IIFE form:
    (function(){ ... return X; })();
Two kinds of pits:

1. **Direct transmission** — after wrap, it becomes `function(){(function(){...return X;})();}`,
   There is no return in the outer layer, **Python side gets None**, and the return value of IIFE is lost.

2. **Manually add `"return " + iife_js` prefix** - It seems to be solved, but when iife_js string
   There is a newline at the beginning (this is usually the case for multi-line constant strings), and after wrapping it becomes:
        function(){return
        (function(){...return X;})();}
   JavaScript's **ASI (Automatic Semicolon Insertion)** rules state:
   There cannot be a LineTerminator between the `return` keyword and the next token, otherwise the semicolon will be automatically added.
   → What is actually executed is `return; (function(){...})();`, and the IIFE expression is discarded.
   **Python side still gets None**. Actual test verification.

## solve

Use `var __r = IIFE; return __r;` to cache the intermediate results and then return. `var` followed by a newline
Not subject to ASI restrictions (var declarations can span lines) and regardless of how much whitespace/newline there is before or after the IIFE string
All can work stably.

## use

    from social_uploader.tools.js_runner import run_iife
    result = run_iife(page, _SOME_IIFE_JS)
    result = run_iife(page, _IIFE_WITH_PARAM, element) # Parameter transparent transmission
"""

import logging

logger = logging.getLogger(__name__)


def run_iife(page_or_ele, iife_js: str, *args, timeout=None):
    """Safely obtain return value for JS string of IIFE form `(function(){...return X;})();`.

    Args:
        page_or_ele: DrissionPage page / element / shadow_root object (anything with run_js method).
        iife_js: Complete IIFE expression string. Trailing semicolons and whitespace are automatically stripped.
        *args: Transparently passed to arguments[0..n] inside IIFE (DrissionPage native support).
        timeout: transparently passed to the timeout parameter of page.run_js.

    Returns:
        IIFE The actual value returned.
    """
    body = iife_js.strip().rstrip(";").rstrip()
    wrapped = f"var __dp_iife_r = {body}; return __dp_iife_r;"
    if timeout is not None:
        return page_or_ele.run_js(wrapped, *args, timeout=timeout)
    return page_or_ele.run_js(wrapped, *args)
