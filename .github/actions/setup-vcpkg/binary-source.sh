#!/usr/bin/env bash
# Chooses vcpkg's binary cache mode for this run and exports what vcpkg and the
# AWS CLI need to use it. Called by action.yml; tests/test_setup_vcpkg_binary_source.py
# runs it directly.
#
# Mode, by event (anolishq/.github#176):
#   push or workflow_dispatch on the default branch, schedule -> readwrite, write token
#   anything else (pull_request, other branches, ...)          -> read, read token
#   the token that mode needs is empty (a fork pull request)     -> none
#
# Reads: EVENT, REF, DEFAULT_BRANCH, ENDPOINT, BUCKET, READ_ID, READ_SECRET,
#        WRITE_ID, WRITE_SECRET, RUNNER_TEMP, GITHUB_ENV, GITHUB_OUTPUT.
set -euo pipefail

writer=false
case "$EVENT" in
  schedule) writer=true ;; # scheduled runs always run on the default branch
  push | workflow_dispatch)
    [[ -n "$DEFAULT_BRANCH" && "$REF" == "refs/heads/$DEFAULT_BRANCH" ]] && writer=true
    ;;
esac

mode=none id="" secret=""
if [[ -z "$ENDPOINT" || -z "$BUCKET" ]]; then
  echo "No R2 endpoint or bucket given: building without the remote binary cache."
elif [[ "$writer" == true && -n "$WRITE_ID" && -n "$WRITE_SECRET" ]]; then
  mode=readwrite id=$WRITE_ID secret=$WRITE_SECRET
elif [[ -n "$READ_ID" && -n "$READ_SECRET" ]]; then
  mode=read id=$READ_ID secret=$READ_SECRET
else
  echo "No R2 token for this run (a fork pull request gets none): building without the remote binary cache."
fi

# `default` keeps the job's own packages between builds in one job, whatever
# the remote mode.
sources="clear;default,readwrite"
if [[ "$mode" != none ]]; then
  sources="$sources;x-aws,s3://$BUCKET/vcpkg/,$mode"
  # One PUT per package instead of a multipart upload: a multipart upload of
  # grpc failed with InvalidPart in the #175 spike, and vcpkg reports a failed
  # upload only as a warning. R2 takes a single PUT up to 5 GiB.
  config="$RUNNER_TEMP/vcpkg-aws-config"
  printf '[default]\ns3 =\n  multipart_threshold = 4GB\n' > "$config"
  {
    echo "AWS_ACCESS_KEY_ID=$id"
    echo "AWS_SECRET_ACCESS_KEY=$secret"
    echo "AWS_ENDPOINT_URL_S3=$ENDPOINT"
    echo "AWS_DEFAULT_REGION=auto"
    echo "AWS_CONFIG_FILE=$config"
  } >> "$GITHUB_ENV"
fi
echo "VCPKG_BINARY_SOURCES=$sources" >> "$GITHUB_ENV"
echo "mode=$mode" >> "$GITHUB_OUTPUT"
echo "Binary cache: $mode (event $EVENT, ref $REF)"
echo "VCPKG_BINARY_SOURCES=$sources"
