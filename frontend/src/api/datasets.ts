import {request} from './client';import type {Dataset,DatasetVersion,Point} from '../types/entities';
export const list=()=>request<Dataset[]>('/datasets');
export const create=(data:unknown)=>request<Dataset>('/datasets','POST',data);
export const detail=(id:string)=>request<Dataset&{points:Point[]}>('/datasets/'+id);
export const versions=(id:string)=>request<DatasetVersion[]>('/datasets/'+id+'/versions');
export const versionDetail=(id:string,version:number)=>request<DatasetVersion>('/datasets/'+id+'/versions/'+version);
export const updatePoints=(id:string,data:{csv_text:string;source?:string})=>request<{changed:boolean;dataset:Dataset&{points:Point[]};version:DatasetVersion}>('/datasets/'+id+'/points','PUT',data);
