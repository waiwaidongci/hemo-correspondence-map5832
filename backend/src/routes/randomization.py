from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.config.database import get_db
from src.controllers.dependencies import current_user, writers
from src.schemas.randomization import RandomizationInput
from src.services import randomization_runs

router = APIRouter()


@router.post('/runs/{run_id}/randomization', status_code=201)
def run_test(run_id: int, data: RandomizationInput, db: Session = Depends(get_db),
             user=Depends(writers)):
 data.run_id = run_id
 return randomization_runs.run_randomization(db, data, user)


@router.get('/runs/{run_id}/randomization')
def get_test(run_id: int, db: Session = Depends(get_db), user=Depends(current_user)):
 test = randomization_runs.get_randomization(db, run_id)
 if test is None:
  raise HTTPException(404, '该分析尚未运行固定边际随机检验')
 return test
