#!/usr/bin/env bash

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
. ${DIR}/common.sh

for env in ${ENVS}; do
  env_sanitized=$(echo ${env} | sed -e 's/\//_/g')
  parallel --header : --results $HOME/output/parallel/irl_policies \
           ${EVAL_POLICY_CMD} env_name=${env} policy_type=ppo2 \
           policy_path={policy_path} \
           ::: policy_path $HOME/output/train_adversarial/${env_sanitized}/*/final/gen_policy
done