"""Real measured-stature baseline; explicitly not the Agent's image accuracy."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from evals.height_geometry import calibrate,estimate_height
CAMERAS=('01','02','03','04','05','08','10','11','12')


def read_points(path):
    with path.open(encoding='utf-8-sig') as source:
        return [(float(r['Head.Y']),float(r['Feet.Y']),float(r['Height'])) for r in csv.DictReader(source,delimiter='\t')]


def run(directory):
    calibration=[];cases=[];files=[]
    for ident in CAMERAS:
        folder=directory/ident;reference=folder/'001.txt'
        points=read_points(reference);camera,rms=calibrate(points)
        calibration.append({'camera':ident,'reference_subject':'001','reference_height_cm':points[0][2],
            'observations':len(points),'reprojection_rms_px':round(rms,5),
            'parameters':{'focal_px':camera.focal_px,'tilt_radians':camera.tilt_radians,'height_cm':camera.camera_height_cm}})
        for path in sorted(folder.glob('*.txt')):
            files.append({'path':f'{ident}/{path.name}','sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
            if path==reference:continue
            truth_rows=read_points(path);predictions=[];rejected=0
            assert len({p[2] for p in truth_rows})==1
            for head,foot,_ in truth_rows:
                try:predictions.append(estimate_height(head,foot,camera))
                except ValueError:rejected+=1
            mean=sum(predictions)/len(predictions) if predictions else None;truth=truth_rows[0][2]
            cases.append({'camera':ident,'subject':path.stem,'measured_height_cm':truth,'mean_estimate_cm':round(mean,6) if mean else None,
                'absolute_error_cm':round(abs(mean-truth),6) if mean else None,'observations':len(truth_rows),'rejected_observations':rejected})
    errors=[c['absolute_error_cm'] for c in cases if c['absolute_error_cm'] is not None]
    return {'scope':'measured_height_geometric_baseline_with_human_marked_points_not_agent_accuracy',
        'source':'https://github.com/lishengzhe/ccvs','paper':'https://doi.org/10.1186/s13640-015-0086-1',
        'ground_truth':'Study authors measured stature with shoes before recording, per paper section 3.2.',
        'protocol':'Calibrate each camera using subject 001 only; evaluate every available other subject, no test-height fitting.',
        'image_height_px':720,'cameras':len(calibration),'held_out_camera_subject_groups':len(cases),
        'unique_held_out_subjects':len({c['subject'] for c in cases}),'evaluated_groups':len(errors),
        'mae_cm':sum(errors)/len(errors) if errors else None,'maximum_absolute_error_cm':max(errors) if errors else None,
        'sample_unit':'camera-subject mean; same person across cameras is correlated',
        'model_calls':0,'calibration':calibration,'cases':cases,'input_files':files,
        'limitations':['Manual point annotations exclude detector and tracker error.','Camera assumptions include flat ground and negligible roll/pan.',
            'Not a result of the DeepSeek Agent; the Agent is evaluated separately on image samples.',
            'No lens distortion correction; do not claim reproduction of the paper reported metric.']}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();report=run(args.data)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('calibration','cases','input_files','limitations')}))
