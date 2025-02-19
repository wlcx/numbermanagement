from django.shortcuts import render, redirect
from django.http import HttpResponse, Http404
from .forms import CreateNumberForm, EditNumberForm, DeleteNumberForm, BlockUserForm, JoinGroupForm
from django.contrib.auth.models import User
from users.models import Operator
from numman.models import  Event, Number, TypeOfService, Range
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.conf import settings
import requests
from groups.models import Group, Membership

def getTOSData():
    data =  list(TypeOfService.objects.filter().values())
    newdata = {}
    for item in data:
        del item["privileged"]
        name = item['name']
        del item["name"]
        newdata[name] = item
    return newdata

def getRanges():
    data =  list(Range.objects.filter().values())
    for item in data:
        del item["id"]
        del item["privileged"]
    return data

def operator_required(function):
    def wrapper(request, *args, **kw):
        #u=User.objects.get(username=request.user)
        try:
            u = request.user.operator.isOperator
        except Operator.DoesNotExist:
            u = False        
        if not u:
            raise PermissionDenied()
        else:
            return function(request, *args, **kw)
    return wrapper

def publish(action, number, tos):
    data = {}
    data['number'] = number
    data['tos'] = tos
    headers = {'token': settings.HOOKDECK_TOKEN}
    url = settings.HOOKDECK_URL+'/'+action
    r = requests.post(url, headers=headers, data=data)
    print(r.text)


@login_required
@operator_required
def home(request):
    return render(request, 'oper/home.html', {'title': "Operator View"})

@login_required
@operator_required
def create_number(request):
    if request.method == 'GET':
        first_event = Event.objects.filter(active=True)[0]
        form = CreateNumberForm(initial={'event': first_event})
        context = {'form': form, 'tosdata': getTOSData(), 'ranges': getRanges(), 'userdata' : {"username": request.user.username}, 'title': "Create a Number for User"}
        return render(request, 'oper/create_number.html', context)
    elif request.method == 'POST':
        form = CreateNumberForm(request.POST)
        form.instance.user  = request.user
        if form.is_valid():
            form.save()
            tosGroupObj = TypeOfService.objects.get(name='Group')
            if form.cleaned_data['typeofservice'] == tosGroupObj:
                n = Number.objects.get(pk=form.cleaned_data['value'])
                Group.objects.create(value=n, event=form.cleaned_data['event'], user=form.instance.user)
            publish('add', form.cleaned_data['value'], form.cleaned_data['typeofservice'])
            return redirect('/operator/number')
        else:
            return render(request, 'oper/create_number.html', {'form': form, 'tosdata': getTOSData() })

@login_required
@operator_required
def my_numbers(request):
    numbers = Number.objects.filter()
    context = {'numbers': numbers, 'title': "Manage all Numbers"}
    return render(request, 'oper/mynumbers.html', context)


@login_required
@operator_required
def edit_number(request, id):
    number = Number.objects.filter(value=id).first()
    if number == None:
        raise Http404
    else:
        if request.method == 'GET':
            context = {'form': EditNumberForm(instance=number), 'id': id, 'title': "Edit "+str(id)}
            return render(request,'form.html',context)
        elif request.method == 'POST':
            form = EditNumberForm(request.POST, instance=number)
            if form.is_valid():
                form.save()
                publish('remove', id, number.typeofservice )
                messages.success(request, 'The number has been updated successfully.')
                return redirect('/operator/number')
            else:
                messages.error(request, 'Please correct the following errors:')
                return render(request,'form',{'form':form, 'id': id, 'title': "Edit "+str(id)})

@login_required
@operator_required
def delete_number(request, id):
    number = Number.objects.filter(value=id).first()
    if number == None:
        raise Http404
    else:
        if request.method == 'GET':
            context = {'form': DeleteNumberForm(), 'id': id, 'title' : "Delete "+str(id)}
            return render(request,'form.html', context)
        elif request.method == 'POST':
            form = DeleteNumberForm(request.POST)
            if form.is_valid():
                data = form.cleaned_data
                print(data['checknumber'])
                print(id)
                if int(data['checknumber']) == int(id):
                    number = Number.objects.get(value=id)
                    number.delete()
                    publish('remove', id, number.typeofservice )
                    messages.success(request, 'The number has been deleted.')
                else:
                    messages.error(request, 'The confirmation did not match.')
            else:
                messages.error(request, 'Invalid Form')
        return redirect('/operator/number')
    

@login_required
@operator_required
def block_user(request):
    if request.method == 'GET':
        context = {'form': BlockUserForm(), 'title' : "Account Blocking"}
        return render(request,'oper/block_user.html', context)
    elif request.method == 'POST':
        form = BlockUserForm(request.POST)
        print(form)
        if form.is_valid():
            data = form.cleaned_data
            user = data['username']
            user.is_active = data['is_active']
            user.save()
        else:
            messages.error(request, 'Invalid Form')
    return redirect('/operator')


@login_required
@operator_required
def list_groups(request):
    groups = Group.objects.values('value')
    context = {'groups': groups, 'title': "All Groups"}
    return render(request, 'oper/listgroups.html', context)


@login_required
@operator_required
def manage_group(request, id):
    group = Group.objects.select_related("value").filter(value=id).first()
    if group == None:
        raise Http404
    else:
        if request.method == 'GET':
            members = Membership.objects.select_related("member").filter(group=group).values("member_id", "member__label", "delay")
            joinform = JoinGroupForm(group=group)
            context = {'members': members, 'group': group, 'joinform': joinform, 'title': "Group "+str(id)}
            return render(request, 'oper/managegroup.html', context)
        elif request.method == 'POST':
            joinform = JoinGroupForm(request.POST, group=group)
            joinform.instance.group=group
            if joinform.is_valid():
                joinform.save()
                publish('updategroup', id, 'Group')
                mid = joinform.cleaned_data['member']
                messages.success(request, str(mid)+' addded to Group: '+str(id))
            return redirect('/operator/group/'+str(id))

@login_required
@operator_required
def leave_group(request, gid, mid):
    group = Group.objects.select_related("value").filter(value=gid).first() 
    if group == None:
        raise Http404
    member = Membership.objects.get(group=gid, member=mid)
    member.delete()
    publish('updategroup', gid, 'Group')
    messages.success(request, str(mid)+' removed from Group: '+str(gid))
    return redirect('/operator/group/'+str(gid))
