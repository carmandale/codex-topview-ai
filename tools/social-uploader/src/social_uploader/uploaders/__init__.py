def should_skip(step, resume_from, steps):
    """If resume_from specifies a step, all stages before that step are skipped."""
    if not resume_from:
        return False
    if resume_from not in steps:
        return False
    return steps.index(step) < steps.index(resume_from)
