class CreatorSkillError(RuntimeError):
    """Base error shown to CLI users."""


class ExternalCommandError(CreatorSkillError):
    """An external dependency returned a non-zero exit status."""


class ValidationError(CreatorSkillError):
    """Input or generated output failed validation."""

