# Convenience wrappers for the on-demand jobs (see jobs/ and README.md).
NS := posda
KUBECTL := kubectl -n $(NS)

.PHONY: sync debug debug-clean

# Update the code checkout on the posda-deploy PVC from the repo's master
# branch, following the Job's logs until it finishes.
sync:
	$(KUBECTL) delete job sync-deploy --ignore-not-found
	$(KUBECTL) apply -f jobs/sync-deploy.yaml
	$(KUBECTL) logs -f --pod-running-timeout=2m job/sync-deploy

# Start (or reuse) the debug pod and drop into a shell on the posda-deploy
# PVC. Run `make debug-clean` when done.
debug:
	$(KUBECTL) apply -f jobs/debug-deploy.yaml
	$(KUBECTL) wait --for=condition=Ready --timeout=2m pod/debug-deploy
	@$(KUBECTL) exec -it debug-deploy -- bash || true

debug-clean:
	$(KUBECTL) delete pod debug-deploy --ignore-not-found

shell:
	# $(KUBECTL) exec -it deploy/posda -- bash
	$(KUBECTL) exec -it deploy/posda -- bash -c "cd posdatools; ./posda_shell"
