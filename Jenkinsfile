pipeline {
    agent any

    stages {
        stage('Checkout') {
            steps {
                checkout scmGit(branches: [[name: '*/Socket_devops']], extensions: [], userRemoteConfigs: [[url: 'https://github.com/Apeksha-Math/Socket_devops.git']])
            }
        }
        stage('Build'){
            steps{
                git branch: 'Socket_devops', url: 'https://github.com/Apeksha-Math/Socket_devops.git'
                // bat 'python simplecode.py'
            }
        }
        stage('Test'){
            steps{
                echo 'the job has been tested'
            }
        }
    }
}