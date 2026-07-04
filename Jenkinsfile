pipeline {
    agent any

    environment {
        SERVICES = 'api gateway'
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Build') {
            steps {
                sh 'docker --version'
                sh 'docker compose build'
            }
        }

        stage('Test') {
            steps {
                sh 'echo Running Tests'
            }
        }
    }
}
