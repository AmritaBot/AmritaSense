# Exception System

AmritaSense defines a small set of runtime exceptions used by the interpreter, dependency injection, and control flow primitives.

## InterruptNotice

`InterruptNotice` is a `BaseException` subclass used to terminate workflow execution immediately. It bypasses normal `Exception` handlers and is caught by the interpreter at the top level.

Use cases:

- external stop requests
- emergency termination points in the workflow

## NullPointerException

Raised when a node cannot be found at a specified address or when an alias does not exist.

## BreakLoop

Used internally by loop constructs to implement break semantics. Raising `BreakLoop` exits the current loop body and continues execution after the loop.

## DependsException

Base exception for all dependency injection failures.

## DependsResolveFailed

Raised when dependency resolution fails for a node or callback. This can happen when a required dependency is missing or cannot be matched.

## DependsInjectFailed

Raised when dependencies are resolved successfully but cannot be injected into the target function due to mismatched parameters or runtime resolution failures.
