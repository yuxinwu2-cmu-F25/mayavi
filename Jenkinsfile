// ─────────────────────────────────────────────────────────────────────────────
// Jenkinsfile – Mayavi Code Quality & Hadoop MapReduce Pipeline
//
// Flow:
//   1. Checkout forked mayavi repo
//   2. Run SonarQube static analysis
//   3. Check SonarQube results for BLOCKER issues
//   4a. If blockers found  → abort, do NOT run Hadoop job
//   4b. If no blockers     → upload repo to GCS, submit Dataproc MapReduce job
//   5. Download and display Hadoop job results
// ─────────────────────────────────────────────────────────────────────────────

pipeline {
    agent {
        kubernetes {
            label 'gcloud-agent'
            defaultContainer 'gcloud'
        }
    }

    environment {
        // Build-unique paths (computed here; all other vars read via env.VAR at use-site)
        OUTPUT_PATH = "output/build-${env.BUILD_NUMBER}"
        REPO_DIR    = "${env.WORKSPACE}/mayavi-src"
    }

    stages {

        // ── Stage 1: Checkout ────────────────────────────────────────────────
        stage('Checkout') {
            steps {
                container('gcloud') {
                    sh """
                        git clone --depth 1 \
                            https://github.com/${env.GITHUB_USERNAME}/mayavi.git \
                            ${REPO_DIR}
                    """
                }
            }
        }

        // ── Stage 2: SonarQube Analysis ──────────────────────────────────────
        stage('SonarQube Analysis') {
            steps {
                container('sonar-scanner') {
                    withSonarQubeEnv('SonarQube') {
                        sh """
                            sonar-scanner \
                                -Dsonar.projectKey=mayavi \
                                -Dsonar.projectName='Mayavi' \
                                -Dsonar.sources=${REPO_DIR} \
                                -Dsonar.inclusions='**/*.py' \
                                -Dsonar.python.version=3
                        """
                    }
                }
            }
        }

        // ── Stage 3: Quality Gate / Blocker Check ────────────────────────────
        stage('Check for Blocker Issues') {
            steps {
                container('gcloud') {
                    script {
                        // Wait up to 5 minutes for SonarQube to finish analysis
                        timeout(time: 5, unit: 'MINUTES') {
                            sleep(time: 30, unit: 'SECONDS')  // brief delay for SQ processing

                            def sonarHostUrl = env.SONAR_HOST_URL ?: 'http://sonarqube-sonarqube.cicd.svc.cluster.local:9000'
                            def sonarToken   = env.SONAR_TOKEN ?: ''

                            def response = sh(
                                script: """
                                    curl -sf -u "${sonarToken}:" \
                                        "${sonarHostUrl}/api/issues/search?projectKeys=mayavi&types=BUG,VULNERABILITY,CODE_SMELL&severities=BLOCKER&resolved=false&ps=1"
                                """,
                                returnStdout: true
                            ).trim()

                            def json         = readJSON text: response
                            def blockerCount = json.total as Integer

                            if (blockerCount > 0) {
                                echo "╔══════════════════════════════════════════════╗"
                                echo "║  BLOCKER issues found: ${blockerCount}              ║"
                                echo "║  Hadoop job will NOT run.                    ║"
                                echo "╚══════════════════════════════════════════════╝"
                                currentBuild.result = 'UNSTABLE'
                                env.HAS_BLOCKERS = 'true'
                            } else {
                                echo "No BLOCKER issues found. Hadoop job will proceed."
                                env.HAS_BLOCKERS = 'false'
                            }
                        }
                    }
                }
            }
        }

        // ── Stage 4: Upload Repo Files to GCS ────────────────────────────────
        stage('Upload Repo to GCS') {
            when {
                expression { env.HAS_BLOCKERS == 'false' }
            }
            steps {
                container('gcloud') {
                    sh """
                        # Clear previous input and upload fresh copy
                        gsutil -q rm -rf gs://${env.HADOOP_INPUT_BUCKET}/input/ || true
                        gsutil -m cp -r ${REPO_DIR}/* gs://${env.HADOOP_INPUT_BUCKET}/input/
                    """
                }
            }
        }

        // ── Stage 5: Submit Hadoop Streaming MapReduce Job ───────────────────
        stage('Submit Hadoop Job') {
            when {
                expression { env.HAS_BLOCKERS == 'false' }
            }
            steps {
                container('gcloud') {
                    script {
                        // Remove previous output so Hadoop doesn't complain
                        sh """
                            gsutil -q rm -rf gs://${env.HADOOP_OUTPUT_BUCKET}/${OUTPUT_PATH}/ || true
                        """

                        def jobId = sh(
                            script: """
                                gcloud dataproc jobs submit hadoop \
                                    --cluster=${env.DATAPROC_CLUSTER} \
                                    --region=${env.DATAPROC_REGION} \
                                    --project=${env.GCP_PROJECT} \
                                    --jar=file:///usr/lib/hadoop/hadoop-streaming.jar \
                                    -- \
                                    -files gs://${env.DATAPROC_STAGING_BUCKET}/scripts/mapper.py,gs://${env.DATAPROC_STAGING_BUCKET}/scripts/reducer.py \
                                    -mapper  "python3 mapper.py" \
                                    -reducer "python3 reducer.py" \
                                    -input   "gs://${env.HADOOP_INPUT_BUCKET}/input/" \
                                    -output  "gs://${env.HADOOP_OUTPUT_BUCKET}/${OUTPUT_PATH}" \
                                    --format='value(reference.jobId)'
                            """,
                            returnStdout: true
                        ).trim()

                        echo "Submitted Dataproc job: ${jobId}"
                        env.DATAPROC_JOB_ID = jobId
                    }
                }
            }
        }

        // ── Stage 6: Display Results ─────────────────────────────────────────
        stage('Display Hadoop Results') {
            when {
                expression { env.HAS_BLOCKERS == 'false' }
            }
            steps {
                container('gcloud') {
                    sh """
                        echo "════════════════════════════════════════"
                        echo "  Hadoop MapReduce Results (Line Count)"
                        echo "════════════════════════════════════════"

                        # Merge and print all output parts
                        gsutil cat "gs://${env.HADOOP_OUTPUT_BUCKET}/${OUTPUT_PATH}/part-*"

                        echo "════════════════════════════════════════"
                        echo "  Full output stored at:"
                        echo "  gs://${env.HADOOP_OUTPUT_BUCKET}/${OUTPUT_PATH}/"
                        echo "════════════════════════════════════════"
                    """
                }
            }
        }
    }

    // ── Post Actions ─────────────────────────────────────────────────────────
    post {
        success {
            echo "Pipeline completed successfully."
        }
        unstable {
            echo "Pipeline completed with BLOCKER issues detected. Hadoop job was skipped."
        }
        failure {
            echo "Pipeline failed. Check stage logs above."
        }
        always {
            // Clean up local clone to free pod storage
            sh "rm -rf ${env.REPO_DIR} || true"
        }
    }
}
