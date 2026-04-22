import { describe, it, expect, beforeEach } from 'vitest';
import { BackgroundTaskManager } from '../src/client/BackgroundTasks.js';

describe('BackgroundTaskManager', () => {
  let mgr: BackgroundTaskManager;

  beforeEach(() => {
    mgr = new BackgroundTaskManager();
  });

  it('creates a task with auto-generated name', () => {
    const task = mgr.createTask('jenkins-cicd', 'build pg-acquiring-biz', []);
    expect(task.id).toBe(1);
    expect(task.displayName).toBe('build:pg-acquiring-biz');
    expect(task.status).toBe('running');
  });

  it('increments task IDs', () => {
    const t1 = mgr.createTask('a', 'task 1', []);
    const t2 = mgr.createTask('b', 'task 2', []);
    expect(t2.id).toBe(t1.id + 1);
  });

  it('lists all tasks', () => {
    mgr.createTask('a', 'task 1', []);
    mgr.createTask('b', 'task 2', []);
    expect(mgr.listTasks()).toHaveLength(2);
  });

  it('gets task by ID', () => {
    const task = mgr.createTask('a', 'hello', []);
    expect(mgr.getTask(task.id)).toBe(task);
    expect(mgr.getTask(999)).toBeUndefined();
  });

  it('removes task', () => {
    const task = mgr.createTask('a', 'hello', []);
    mgr.removeTask(task.id);
    expect(mgr.listTasks()).toHaveLength(0);
  });

  it('counts active tasks', () => {
    mgr.createTask('a', 'task 1', []);
    mgr.createTask('b', 'task 2', []);
    expect(mgr.activeCount()).toBe(2);
  });

  it('completes a task as done', () => {
    const task = mgr.createTask('a', 'build something', []);
    mgr.completeTask(task.id, 'BUILD #123 SUCCESS', null);
    expect(task.status).toBe('done');
    expect(task.fullResponse).toBe('BUILD #123 SUCCESS');
    expect(task.resultSummary).toBe('BUILD #123 SUCCESS');
  });

  it('completes a task as error', () => {
    const task = mgr.createTask('a', 'build', []);
    mgr.completeTask(task.id, null, 'Connection refused');
    expect(task.status).toBe('error');
    expect(task.error).toBe('Connection refused');
  });

  it('returns done tasks', () => {
    const t1 = mgr.createTask('a', 'task 1', []);
    mgr.createTask('b', 'task 2', []);
    mgr.completeTask(t1.id, 'done', null);
    expect(mgr.doneTasks()).toHaveLength(1);
  });

  it('generates task names from keywords', () => {
    const t1 = mgr.createTask('a', 'deploy payment-service to prod', []);
    expect(t1.displayName).toBe('deploy:payment-service');

    const t2 = mgr.createTask('a', 'run tests for everything', []);
    // 'test' keyword matches before 'run' in priority order
    expect(t2.displayName).toBe('test:a');

    const t3 = mgr.createTask('auto-pilot', 'explain this code', []);
    expect(t3.displayName).toBe('task:auto-pilot');
  });

  it('canCreate respects max concurrent', () => {
    expect(mgr.canCreate()).toBe(true);
    mgr.createTask('a', 'task 1', []);
    mgr.createTask('b', 'task 2', []);
    mgr.createTask('c', 'task 3', []);
    expect(mgr.canCreate()).toBe(false);
  });

  it('formats task list', () => {
    mgr.createTask('jenkins-cicd', 'build my-app', []);
    const output = mgr.formatTaskList();
    expect(output).toContain('#1');
    expect(output).toContain('build:my-app');
    expect(output).toContain('running');
  });

  it('formats empty task list', () => {
    expect(mgr.formatTaskList()).toBe('  No background tasks.');
  });
});
