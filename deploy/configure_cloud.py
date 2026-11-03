"""Create deployment-only access settings without printing or committing credentials."""
from pathlib import Path
import argparse,os,re,secrets

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--domain',required=True);args=parser.parse_args()
    if not re.fullmatch(r'(?=.{4,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}',args.domain):
        parser.error('Provide a hostname only, such as trace.example.com')
    path=Path(__file__).resolve().parent/'cloud.env'
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w',encoding='utf8',newline='\n') as output:
        output.write('TRACE_DOMAIN='+args.domain+'\nTRACE_WEB_PASSWORD='+secrets.token_urlsafe(24)+'\n')
    print('Created deploy/cloud.env (private). Username: trace. Read the password from this file locally.')
    print('Start: docker compose --env-file deploy/cloud.env -f deploy/compose.cloud.yaml up -d --build')

if __name__=='__main__':main()
