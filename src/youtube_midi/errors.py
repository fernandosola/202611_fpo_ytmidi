"""Errors surfaced by the CLI with stable exit codes."""


class ProjectError(Exception):
    exit_code = 1


class DependencyError(ProjectError):
    exit_code = 3


class DownloadError(ProjectError):
    exit_code = 4


class AudioError(ProjectError):
    exit_code = 5


class TranscriptionError(ProjectError):
    exit_code = 6


class MidiError(ProjectError):
    exit_code = 7
