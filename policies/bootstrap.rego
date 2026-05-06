# bootstrap.rego
# This file ensures OPA starts with a valid bundle.
# Real policies are in infra.rego and canary.rego.
package bootstrap

ready := true
