/** Local CD: deploy only the latest successful master workflow, never a PR.
 * Run: node scripts/deploy-agent.mjs --watch  (or --once)
 * Uses the existing local gh login; stores no GitHub token.
 */
import {execFileSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const stateDir = path.join(root, '.deploy');
const stateFile = path.join(stateDir, 'state.json');
const envFile = path.join(root, '.env');
const repo = 'asartem9855/PTLab2';
const gh = process.platform === 'win32' && fs.existsSync('C:/Program Files/GitHub CLI/gh.exe')
  ? 'C:/Program Files/GitHub CLI/gh.exe' : 'gh';
fs.mkdirSync(stateDir, {recursive:true});
if (!fs.existsSync(envFile)) throw Error('Create .env before starting local CD');
const log = message => {
  const line = `${new Date().toISOString()} ${message}`;
  console.log(line);
  fs.appendFileSync(path.join(stateDir, 'deploy.log'), line+'\n');
};
function command(exe, args, options={}) {
  return execFileSync(exe,args,{encoding:'utf8',windowsHide:true,maxBuffer:20*1024*1024,...options});
}
function compose(release, sha, args) {
  return command('docker', ['compose', '--project-name', 'tp-stationery',
    '--env-file',envFile,'-f',path.join(release,'compose.yaml'),...args], {
      env:{...process.env, SHOP_IMAGE:`tp-stationery:${sha}`},
      timeout:20*60*1000,
  });
}
function deploy() {
  const runs = JSON.parse(command(gh,['run','list','--repo',repo,
    '--workflow','ci-cd.yml','--branch','master','--event','push',
    '--status','success','--limit','1','--json','databaseId,headSha,url']));
  if (!runs.length) { log('No successful master delivery yet'); return; }
  const run = runs[0];
  if (!/^[a-f0-9]{40}$/.test(run.headSha)) throw Error('Invalid commit SHA');
  const previous = fs.existsSync(stateFile) ? JSON.parse(fs.readFileSync(stateFile,'utf8')) : null;
  if (previous?.sha === run.headSha) return;
  // A completed older run must not overwrite a newer master commit whose CI is pending.
  const latest = command(gh,['api',`repos/${repo}/commits/master`,'--jq','.sha']).trim();
  if (latest !== run.headSha) { log('Latest master is still waiting for successful CI'); return; }
  const release = path.join(stateDir,'releases',run.headSha);
  const bundle = path.join(stateDir,'bundles',run.headSha,String(Date.now()));
  fs.mkdirSync(release,{recursive:true});
  fs.mkdirSync(bundle,{recursive:true});
  log(`Deploying ${run.headSha} from verified run ${run.databaseId}`);
  command(gh,['run','download',String(run.databaseId),'--repo',repo,
    '--name','lab23-deployment','--dir',bundle],{timeout:120000});
  command('tar',['-xf',path.join(bundle,'source.zip'),'-C',release]);
  compose(release,run.headSha,['build','web']);
  try {
    compose(release,run.headSha,['up','-d','--no-build','--wait','--wait-timeout','180']);
  } catch(error) {
    if (previous && fs.existsSync(previous.release)) {
      log(`Deployment failed; restoring application image ${previous.sha}`);
      compose(previous.release,previous.sha,['up','-d','--no-build','--wait']);
    }
    throw error;
  }
  fs.writeFileSync(stateFile,JSON.stringify({sha:run.headSha,run:run.url,
    release,deployedAt:new Date().toISOString()},null,2));
  log(`Healthy: http://localhost:8000/ (${run.headSha.slice(0,7)})`);
}
const watch = process.argv.includes('--watch');
const lock = path.join(stateDir,'agent.lock');
try {
  const fd = fs.openSync(lock,'wx');
  fs.writeFileSync(fd,String(process.pid));
  fs.closeSync(fd);
} catch {
  throw Error(`Another agent may be running; inspect ${lock} before restarting`);
}
const cleanup = () => { try {fs.unlinkSync(lock);} catch {} };
process.on('exit',cleanup);
process.on('SIGINT',()=>process.exit(0));
process.on('SIGTERM',()=>process.exit(0));
log(`Local deployment agent started, PID ${process.pid}`);
do {
  try { deploy(); }
  catch(error) {
    log(`Deployment error: ${error.message}`);
    if (!watch) {process.exitCode=1;break;}
  }
  if (watch) await new Promise(resolve=>setTimeout(resolve,60000));
} while(watch);
